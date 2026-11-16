"""Checkpoint-safe micro-batch execution for Ronin streaming runtimes."""

from __future__ import annotations

from collections.abc import Callable, Mapping
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


@dataclass(frozen=True, slots=True)
class StreamSupervisorResult:
    """Bounded aggregate receipt for repeated checkpoint-safe micro-batches."""

    stream_id: str
    status: str
    stop_reason: str
    batches: int
    records: int
    rows: int
    previous_checkpoint: StreamCheckpoint
    next_checkpoint: StreamCheckpoint


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

    def run_until_idle(
        self,
        stream_id: str,
        *,
        limit: int = 1000,
        timeout_seconds: float = 1.0,
        max_batches: int = 100,
        max_records: int | None = None,
        idle_polls: int = 3,
        stop_requested: Callable[[], bool] | None = None,
    ) -> StreamSupervisorResult:
        """Drain repeated micro-batches without allowing an unbounded run.

        Every non-empty batch is committed through :meth:`run_once`, so a
        provider failure leaves the last durable checkpoint as the recovery
        boundary. The supervisor stops at the first empty poll, an explicit
        cap, or a cooperative stop request; it never waits indefinitely for a
        source or accumulates records in memory across batches.
        """

        if (
            not isinstance(max_batches, int)
            or isinstance(max_batches, bool)
            or not 1 <= max_batches <= 100_000
        ):
            raise ValueError("stream max_batches must be an integer between 1 and 100000")
        if max_records is not None and (
            not isinstance(max_records, int)
            or isinstance(max_records, bool)
            or not 1 <= max_records <= 10_000_000
        ):
            raise ValueError("stream max_records must be an integer between 1 and 10000000")
        if (
            not isinstance(idle_polls, int)
            or isinstance(idle_polls, bool)
            or not 1 <= idle_polls <= 10
        ):
            raise ValueError("stream idle_polls must be an integer between 1 and 10")

        initial = self._checkpoints.get(stream_id)
        batches = 0
        records = 0
        rows = 0
        next_checkpoint = initial
        stop_reason = "idle"
        empty_polls = 0
        while True:
            if stop_requested is not None and stop_requested():
                stop_reason = "stop_requested"
                status = "stopped"
                break
            if batches >= max_batches:
                stop_reason = "max_batches"
                status = "limit_reached"
                break
            remaining = None if max_records is None else max_records - records
            if remaining == 0:
                stop_reason = "max_records"
                status = "limit_reached"
                break
            batch_limit = limit if remaining is None else min(limit, remaining)
            result = self.run_once(
                stream_id,
                limit=batch_limit,
                timeout_seconds=timeout_seconds,
            )
            if result.records == 0:
                empty_polls += 1
                if empty_polls >= idle_polls:
                    stop_reason = "idle"
                    status = "succeeded" if records else "idle"
                    break
                continue
            empty_polls = 0
            batches += 1
            records += result.records
            rows += result.rows
            next_checkpoint = result.next_checkpoint

        return StreamSupervisorResult(
            stream_id,
            status,
            stop_reason,
            batches,
            records,
            rows,
            initial,
            next_checkpoint,
        )


__all__ = (
    "IdentityTransform",
    "MicroBatchProcessor",
    "MicroBatchResult",
    "StreamSupervisorResult",
    "StreamCheckpointConflict",
    "StreamTransform",
)
