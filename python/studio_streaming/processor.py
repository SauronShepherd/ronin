"""Checkpoint-safe micro-batch execution for Ronin streaming runtimes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .contracts import (
    StreamBatch,
    StreamCheckpoint,
    StreamCheckpointStore,
    StreamSink,
    StreamSinkCommit,
    StreamSource,
)


class StreamCheckpointConflict(RuntimeError):
    """Raised when another processor advances a stream checkpoint concurrently."""


@runtime_checkable
class StreamTransform(Protocol):
    def apply(self, batch: StreamBatch) -> tuple[Mapping[str, object], ...]: ...


class IdentityTransform:
    def apply(self, batch: StreamBatch) -> tuple[Mapping[str, object], ...]:
        return tuple(dict(record.value) for record in batch.records)


@dataclass(frozen=True, slots=True)
class MicroBatchResult:
    stream_id: str
    previous_checkpoint: StreamCheckpoint
    next_checkpoint: StreamCheckpoint
    records: int
    rows: int
    sink_commit: StreamSinkCommit | None


class MicroBatchProcessor:
    """Poll, transform, commit sink output, then CAS the durable source checkpoint."""

    def __init__(
        self,
        source: StreamSource,
        sink: StreamSink,
        checkpoints: StreamCheckpointStore,
        transform: StreamTransform | None = None,
    ) -> None:
        self._source = source
        self._sink = sink
        self._checkpoints = checkpoints
        self._transform = transform or IdentityTransform()

    def run_once(
        self,
        stream_id: str,
        *,
        limit: int = 1000,
        timeout_seconds: float = 1.0,
    ) -> MicroBatchResult:
        if not stream_id or stream_id != stream_id.strip():
            raise ValueError("stream_id must be non-empty and trimmed")
        if limit < 1 or limit > 100_000:
            raise ValueError("stream batch limit must be between 1 and 100000")
        if timeout_seconds < 0 or timeout_seconds > 300:
            raise ValueError("stream timeout_seconds must be in [0, 300]")

        previous = self._checkpoints.get(stream_id)
        batch = self._source.poll(
            previous,
            limit=limit,
            timeout_seconds=timeout_seconds,
        )
        if not batch.records:
            if batch.checkpoint != previous:
                raise ValueError("empty stream batch must not advance checkpoint")
            return MicroBatchResult(
                stream_id,
                previous,
                previous,
                0,
                0,
                None,
            )

        for position in previous.positions:
            next_offset = batch.checkpoint.offset_for(position.partition)
            if next_offset is not None and next_offset < position.offset:
                raise ValueError("stream source checkpoint must not move backwards")

        rows = tuple(self._transform.apply(batch))
        commit = self._sink.write(stream_id, batch, rows)
        if commit.rows != len(rows):
            raise ValueError("stream sink commit row count does not match transformed rows")
        if commit.checkpoint_digest != batch.checkpoint.digest:
            raise ValueError("stream sink commit checkpoint digest does not match batch")

        if not self._checkpoints.compare_and_set(
            stream_id,
            previous,
            batch.checkpoint,
        ):
            raise StreamCheckpointConflict(
                "stream checkpoint changed after sink commit; sink output must be replay-safe"
            )
        return MicroBatchResult(
            stream_id,
            previous,
            batch.checkpoint,
            len(batch.records),
            len(rows),
            commit,
        )


__all__ = (
    "IdentityTransform",
    "MicroBatchProcessor",
    "MicroBatchResult",
    "StreamCheckpointConflict",
    "StreamTransform",
)
