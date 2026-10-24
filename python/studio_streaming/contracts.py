"""Provider-neutral streaming contracts for Ronin Public v1."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias, cast, runtime_checkable

from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.canonical_json import encode as encode_canonical_json

StreamDataType: TypeAlias = Literal[
    "bool", "date", "decimal", "float64", "int64", "json", "string", "timestamp"
]


def _definition_text(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\n" in value
        or "\r" in value
        or "\x00" in value
    ):
        raise ValueError(f"stream definition {name} must be non-empty, trimmed, and single-line")
    folded = value.casefold()
    if folded.startswith("bearer ") or "-----begin " in folded or "password=" in folded:
        raise ValueError(f"stream definition {name} must not contain credential material")
    return value


@dataclass(frozen=True, order=True, slots=True)
class StreamSchemaField:
    name: str
    data_type: StreamDataType
    nullable: bool = True

    def __post_init__(self) -> None:
        _definition_text(self.name, "schema field name")
        if self.data_type not in {
            "bool",
            "date",
            "decimal",
            "float64",
            "int64",
            "json",
            "string",
            "timestamp",
        }:
            raise ValueError("unsupported stream schema data_type")
        if not isinstance(self.nullable, bool):
            raise ValueError("stream schema nullable must be boolean")

    def to_payload(self) -> dict[str, object]:
        return {"name": self.name, "data_type": self.data_type, "nullable": self.nullable}

    @classmethod
    def from_payload(cls, payload: object) -> StreamSchemaField:
        if not isinstance(payload, Mapping) or set(payload) != {"name", "data_type", "nullable"}:
            raise ValueError("stream schema field has invalid shape")
        name, data_type, nullable = (payload[key] for key in ("name", "data_type", "nullable"))
        if not isinstance(name, str) or not isinstance(data_type, str):
            raise ValueError("stream schema field identity must be strings")
        if not isinstance(nullable, bool):
            raise ValueError("stream schema nullable must be boolean")
        return cls(name, cast(StreamDataType, data_type), nullable)


@dataclass(frozen=True, slots=True)
class StreamSourceDefinition:
    connection_id: str
    resource: str
    partitions: tuple[int, ...]
    format: Literal["json"] = "json"

    def __post_init__(self) -> None:
        _definition_text(self.connection_id, "source connection_id")
        _definition_text(self.resource, "source resource")
        if self.format != "json":
            raise ValueError("unsupported stream source format")
        partitions = tuple(sorted(self.partitions))
        if not partitions or any(
            not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in partitions
        ):
            raise ValueError("stream source partitions must be non-negative integers")
        if len(partitions) != len(set(partitions)):
            raise ValueError("stream source partitions must be unique")
        object.__setattr__(self, "partitions", partitions)

    def to_payload(self) -> dict[str, object]:
        return {
            "connection_id": self.connection_id,
            "resource": self.resource,
            "partitions": list(self.partitions),
            "format": self.format,
        }

    @classmethod
    def from_payload(cls, payload: object) -> StreamSourceDefinition:
        if not isinstance(payload, Mapping) or set(payload) != {
            "connection_id",
            "resource",
            "partitions",
            "format",
        }:
            raise ValueError("stream source definition has invalid shape")
        connection_id, resource, partitions, format_name = (
            payload[key] for key in ("connection_id", "resource", "partitions", "format")
        )
        if (
            not isinstance(connection_id, str)
            or not isinstance(resource, str)
            or not isinstance(partitions, list)
            or not all(isinstance(item, int) and not isinstance(item, bool) for item in partitions)
            or not isinstance(format_name, str)
        ):
            raise ValueError("stream source definition fields have invalid types")
        if format_name != "json":
            raise ValueError("unsupported stream source format")
        return cls(connection_id, resource, tuple(partitions), cast(Literal["json"], format_name))


@dataclass(frozen=True, slots=True)
class StreamSinkDefinition:
    kind: Literal["parquet", "table"]
    target_ref: str
    mode: Literal["append"] = "append"

    def __post_init__(self) -> None:
        _definition_text(self.target_ref, "sink target_ref")
        if self.kind not in {"parquet", "table"}:
            raise ValueError("unsupported stream sink kind")
        if self.mode != "append":
            raise ValueError("unsupported stream sink mode")

    def to_payload(self) -> dict[str, str]:
        return {"kind": self.kind, "target_ref": self.target_ref, "mode": self.mode}

    @classmethod
    def from_payload(cls, payload: object) -> StreamSinkDefinition:
        if not isinstance(payload, Mapping) or set(payload) != {"kind", "target_ref", "mode"}:
            raise ValueError("stream sink definition has invalid shape")
        kind, target_ref, mode = (payload[key] for key in ("kind", "target_ref", "mode"))
        if not all(isinstance(value, str) for value in (kind, target_ref, mode)):
            raise ValueError("stream sink definition fields must be strings")
        if kind not in {"parquet", "table"}:
            raise ValueError("unsupported stream sink kind")
        if mode != "append":
            raise ValueError("unsupported stream sink mode")
        return cls(
            cast(Literal["parquet", "table"], kind),
            target_ref,
            cast(Literal["append"], mode),
        )


@dataclass(frozen=True, slots=True)
class StreamRuntimeBinding:
    profile_id: str
    batch_limit: int = 1000
    timeout_seconds: float = 1.0

    def __post_init__(self) -> None:
        _definition_text(self.profile_id, "runtime profile_id")
        if (
            not isinstance(self.batch_limit, int)
            or isinstance(self.batch_limit, bool)
            or not 1 <= self.batch_limit <= 100_000
        ):
            raise ValueError("stream runtime batch_limit must be between 1 and 100000")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(self.timeout_seconds)
            or not 0 <= self.timeout_seconds <= 300
        ):
            raise ValueError("stream runtime timeout_seconds must be finite and in [0, 300]")
        object.__setattr__(self, "timeout_seconds", float(self.timeout_seconds))

    def to_payload(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "batch_limit": self.batch_limit,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_payload(cls, payload: object) -> StreamRuntimeBinding:
        if not isinstance(payload, Mapping) or set(payload) != {
            "profile_id",
            "batch_limit",
            "timeout_seconds",
        }:
            raise ValueError("stream runtime binding has invalid shape")
        profile_id, batch_limit, timeout_seconds = (
            payload[key] for key in ("profile_id", "batch_limit", "timeout_seconds")
        )
        if not isinstance(profile_id, str):
            raise ValueError("stream runtime profile_id must be a string")
        if not isinstance(batch_limit, int) or isinstance(batch_limit, bool):
            raise ValueError("stream runtime batch_limit must be an integer")
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool):
            raise ValueError("stream runtime timeout_seconds must be numeric")
        return cls(profile_id, batch_limit, float(timeout_seconds))


@dataclass(frozen=True, slots=True)
class StreamDefinition:
    id: str
    name: str
    source: StreamSourceDefinition
    sink: StreamSinkDefinition
    schema: tuple[StreamSchemaField, ...]
    runtime: StreamRuntimeBinding

    def __post_init__(self) -> None:
        _definition_text(self.id, "id")
        _definition_text(self.name, "name")
        fields = tuple(sorted(self.schema, key=lambda item: item.name))
        names = [item.name for item in fields]
        if not fields:
            raise ValueError("stream definition schema must not be empty")
        if len(names) != len(set(names)):
            raise ValueError("stream definition schema field names must be unique")
        object.__setattr__(self, "schema", fields)

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source.to_payload(),
            "sink": self.sink.to_payload(),
            "schema": [item.to_payload() for item in self.schema],
            "runtime": self.runtime.to_payload(),
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_json(cls, payload: str) -> StreamDefinition:
        data = decode_canonical_json(payload)
        if not isinstance(data, Mapping) or set(data) != {
            "id",
            "name",
            "source",
            "sink",
            "schema",
            "runtime",
        }:
            raise ValueError("stream definition has invalid shape")
        identifier, name, source, sink, schema, runtime = (
            data[key] for key in ("id", "name", "source", "sink", "schema", "runtime")
        )
        if not isinstance(identifier, str) or not isinstance(name, str):
            raise ValueError("stream definition identity fields must be strings")
        if not isinstance(schema, list):
            raise ValueError("stream definition schema must be an array")
        return cls(
            identifier,
            name,
            StreamSourceDefinition.from_payload(source),
            StreamSinkDefinition.from_payload(sink),
            tuple(StreamSchemaField.from_payload(item) for item in schema),
            StreamRuntimeBinding.from_payload(runtime),
        )


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
                {"partition": item.partition, "offset": item.offset} for item in self.positions
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
    "StreamDataType",
    "StreamDefinition",
    "StreamPosition",
    "StreamRecord",
    "StreamRuntimeBinding",
    "StreamSchemaField",
    "StreamSinkDefinition",
    "StreamSink",
    "StreamSinkCommit",
    "StreamSourceDefinition",
    "StreamSource",
)
