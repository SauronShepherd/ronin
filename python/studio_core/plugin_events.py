"""Versioned plugin events and bounded in-memory outbox/inbox primitives."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


class PluginEventError(ValueError):
    """Invalid event or an idempotency conflict."""


@dataclass(frozen=True, slots=True)
class PluginEventSchema:
    event_type: str
    schema_version: int
    required_fields: tuple[str, ...] = ()

    def validate(self) -> None:
        if self.schema_version < 1 or not self.event_type.endswith(f".v{self.schema_version}"):
            raise PluginEventError("event schema must use a positive versioned event_type")
        if len(set(self.required_fields)) != len(self.required_fields):
            raise PluginEventError(f"duplicate required field in {self.event_type}")


class PluginEventSchemaRegistry:
    def __init__(self) -> None:
        self._schemas: dict[str, PluginEventSchema] = {}

    def register(self, schema: PluginEventSchema) -> None:
        schema.validate()
        if schema.event_type in self._schemas:
            raise PluginEventError(f"event schema collision: {schema.event_type}")
        self._schemas[schema.event_type] = schema

    def validate(self, event: PluginEvent) -> None:
        schema = self._schemas.get(event.event_type)
        if schema is None:
            raise PluginEventError(f"unknown event schema: {event.event_type}")
        if schema.schema_version != event.schema_version:
            raise PluginEventError(f"event schema version mismatch: {event.event_type}")
        missing = set(schema.required_fields) - set(event.payload)
        if missing:
            raise PluginEventError(
                f"event payload is missing fields for {event.event_type}: {sorted(missing)}"
            )

    @property
    def items(self) -> tuple[PluginEventSchema, ...]:
        return tuple(self._schemas[key] for key in sorted(self._schemas))


@dataclass(frozen=True, slots=True)
class PluginEvent:
    event_id: str
    event_type: str
    schema_version: int
    producer: str
    occurred_at: str
    tenant_id: str
    correlation_id: str
    causation_id: str | None
    payload: dict[str, Any]

    def validate(self) -> None:
        values = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "producer": self.producer,
            "tenant_id": self.tenant_id,
            "correlation_id": self.correlation_id,
        }
        if any(not value or value != value.strip() for value in values.values()):
            raise PluginEventError("event identity fields must be non-empty and trimmed")
        if self.schema_version < 1:
            raise PluginEventError("event schema_version must be positive")
        if not self.event_type.endswith(f".v{self.schema_version}"):
            raise PluginEventError("event_type must end with its schema version")
        if not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z",
            self.occurred_at,
        ):
            raise PluginEventError("occurred_at must be RFC-3339")

    def digest(self) -> str:
        self.validate()
        canonical = json.dumps(
            {
                "event_id": self.event_id,
                "event_type": self.event_type,
                "schema_version": self.schema_version,
                "producer": self.producer,
                "occurred_at": self.occurred_at,
                "tenant_id": self.tenant_id,
                "correlation_id": self.correlation_id,
                "causation_id": self.causation_id,
                "payload": self.payload,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    event: PluginEvent
    digest: str
    published: bool = False


class InMemoryOutbox:
    """Reference outbox with idempotent append and explicit publish marking."""

    def __init__(self, *, max_events: int = 10_000) -> None:
        if max_events < 1:
            raise ValueError("max_events must be positive")
        self._max_events = max_events
        self._records: dict[str, OutboxRecord] = {}

    def append(self, event: PluginEvent) -> OutboxRecord:
        digest = event.digest()
        existing = self._records.get(event.event_id)
        if existing is not None:
            if existing.digest != digest:
                raise PluginEventError(f"outbox event conflict: {event.event_id}")
            return existing
        if len(self._records) >= self._max_events:
            raise PluginEventError("outbox capacity exceeded")
        record = OutboxRecord(event, digest)
        self._records[event.event_id] = record
        return record

    def pending(self, *, limit: int = 100) -> tuple[OutboxRecord, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("pending limit must be between 1 and 1000")
        return tuple(record for record in self._records.values() if not record.published)[:limit]

    def mark_published(self, event_id: str) -> None:
        record = self._records.get(event_id)
        if record is None:
            raise KeyError(event_id)
        self._records[event_id] = OutboxRecord(record.event, record.digest, True)


class InMemoryInbox:
    """Consumer idempotency store: one event effect per consumer/event pair."""

    def __init__(self, *, max_events: int = 100_000) -> None:
        if max_events < 1:
            raise ValueError("max_events must be positive")
        self._max_events = max_events
        self._processed: set[tuple[str, str]] = set()

    def process_once(
        self,
        consumer_id: str,
        event: PluginEvent,
        handler: Callable[[PluginEvent], None],
    ) -> bool:
        event.validate()
        key = (consumer_id, event.event_id)
        if key in self._processed:
            return False
        if len(self._processed) >= self._max_events:
            raise PluginEventError("inbox capacity exceeded")
        handler(event)
        self._processed.add(key)
        return True


def new_event(
    *,
    event_id: str,
    event_type: str,
    producer: str,
    tenant_id: str,
    correlation_id: str,
    occurred_at: str,
    payload: dict[str, Any],
    schema_version: int = 1,
    causation_id: str | None = None,
) -> PluginEvent:
    event = PluginEvent(
        event_id,
        event_type,
        schema_version,
        producer,
        occurred_at,
        tenant_id,
        correlation_id,
        causation_id,
        payload,
    )
    event.validate()
    return event


__all__ = (
    "InMemoryInbox",
    "InMemoryOutbox",
    "OutboxRecord",
    "PluginEvent",
    "PluginEventError",
    "PluginEventSchema",
    "PluginEventSchemaRegistry",
    "new_event",
)
