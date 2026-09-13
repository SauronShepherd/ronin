"""Provider-neutral streaming contracts for Ronin Public v1."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from studio_core.canonical_json import encode as encode_canonical_json


@dataclass(frozen=True, order=True, slots=True)
class StreamPosition:
    partition: int
    offset: int

    def __post_init__(self) -> None:
        if self.partition < 0:
            raise ValueError("stream partition must be non-negative")
        if self.offset < -1:
            raise ValueError("stream offset must be >= -1")


@dataclass(frozen=True, slots=True)
class StreamCheckpoint:
    positions: tuple[StreamPosition, ...] = ()

    def __post_init__(self) -> None:
        positions = tuple(sorted(self.positions))
        partitions = [item.partition for item in positions]
        if len(partitions) != len(set(partitions)):
            raise ValueError("stream checkpoint partitions must be unique")
        object.__setattr__(self, "positions", positions)

    def offset_for(self, partition: int) -> int | None:
        for item in self.positions:
            if item.partition == partition:
                return item.offset
        return None

    @property
    def digest(self) -> str:
        payload = {
            "positions": [
                {"partition": item.partition, "offset": item.offset}
                for item in self.positions
            ]
        }
        return hashlib.sha256(encode_canonical_json(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class StreamRecord:
    partition: int
    offset: int
    timestamp_ms: int | None
    key: str | None
    value: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.partition < 0:
            raise ValueError("stream record partition must be non-negative")
        if self.offset < 0:
            raise ValueError("stream record offset must be non-negative")
        if self.timestamp_ms is not None and self.timestamp_ms < 0:
            raise ValueError("stream record timestamp must be non-negative")
        if self.key is not None and "\x00" in self.key:
            raise ValueError("stream record key must not contain NUL")


@dataclass(frozen=True, slots=True)
class StreamBatch:
    records: tuple[StreamRecord, ...]
    checkpoint: StreamCheckpoint

    def __post_init__(self) -> None:
        records = tuple(sorted(self.records, key=lambda item: (item.partition, item.offset)))
        seen = {(item.partition, item.offset) for item in records}
        if len(seen) != len(records):
            raise ValueError("stream batch positions must be unique")
        latest: dict[int, int] = {}
        for item in records:
            latest[item.partition] = max(latest.get(item.partition, -1), item.offset)
        for partition, offset in latest.items():
            if self.checkpoint.offset_for(partition) != offset:
                raise ValueError("stream batch checkpoint must match latest record offsets")
        object.__setattr__(self, "records", records)


@dataclass(frozen=True, slots=True)
class StreamSinkCommit:
    commit_id: str
    rows: int
    checkpoint_digest: str

    def __post_init__(self) -> None:
        if not self.commit_id or self.commit_id != self.commit_id.strip():
            raise ValueError("stream sink commit_id must be non-empty and trimmed")
        if self.rows < 0:
            raise ValueError("stream sink row count must be non-negative")
        if len(self.checkpoint_digest) != 64:
            raise ValueError("stream checkpoint digest must be sha256 hex")


@runtime_checkable
class StreamSource(Protocol):
    def poll(
        self,
        checkpoint: StreamCheckpoint,
        *,
        limit: int,
        timeout_seconds: float,
    ) -> StreamBatch: ...


@runtime_checkable
class StreamSink(Protocol):
    def write(
        self,
        stream_id: str,
        batch: StreamBatch,
        rows: tuple[Mapping[str, object], ...],
    ) -> StreamSinkCommit: ...


@runtime_checkable
class StreamCheckpointStore(Protocol):
    def get(self, stream_id: str) -> StreamCheckpoint: ...

    def compare_and_set(
        self,
        stream_id: str,
        expected: StreamCheckpoint,
        next_checkpoint: StreamCheckpoint,
    ) -> bool: ...


__all__ = (
    "StreamBatch",
    "StreamCheckpoint",
    "StreamCheckpointStore",
    "StreamPosition",
    "StreamRecord",
    "StreamSink",
    "StreamSinkCommit",
    "StreamSource",
)
