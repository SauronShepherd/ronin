"""Adapter from streaming records to the durable scheduler event inbox."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from studio_core import WorkspaceId
from studio_core.scheduler_events import SchedulerEventId
from studio_orchestrator import Instant
from studio_storage.scheduler_events import (
    EventDelivery,
    SchedulerEventConflict,
    SchedulerEventRecord,
    SchedulerEventStore,
)
from studio_streaming import StreamRecord


def ingest_stream_record(
    store: SchedulerEventStore,
    record: StreamRecord,
    *,
    workspace_id: WorkspaceId,
    stream_id: str,
    received_at: Instant | str,
) -> tuple[EventDelivery, ...]:
    event = _stream_event(
        record,
        workspace_id=workspace_id,
        stream_id=stream_id,
        received_at=received_at,
    )
    return _ingest_event(store, event)


def ingest_stream_records(
    store: SchedulerEventStore,
    records: tuple[StreamRecord, ...],
    *,
    workspace_id: WorkspaceId,
    stream_id: str,
    received_at: Instant | str,
) -> tuple[EventDelivery, ...]:
    """Persist one stream micro-batch through a store's optional bulk API."""

    events = tuple(
        _stream_event(
            record,
            workspace_id=workspace_id,
            stream_id=stream_id,
            received_at=received_at,
        )
        for record in records
    )
    bulk = getattr(store, "ingest_events", None)
    if callable(bulk):
        try:
            return tuple(delivery for event in bulk(events) for delivery in event)
        except SchedulerEventConflict:
            # The legacy bridge deliberately ignores received_at during replay
            # comparison; preserve that contract when a bulk store delegates.
            pass
    return tuple(delivery for event in events for delivery in _ingest_event(store, event))


def _stream_event(
    record: StreamRecord,
    *,
    workspace_id: WorkspaceId,
    stream_id: str,
    received_at: Instant | str,
) -> SchedulerEventRecord:
    if not stream_id or stream_id != stream_id.strip():
        raise ValueError("stream_id must be non-empty and trimmed")
    payload = json.dumps(dict(record.value), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    event_id = SchedulerEventId(f"stream-{stream_id}-{record.partition}-{record.offset}")
    occurred = (
        Instant("1970-01-01T00:00:00.000000Z")
        if record.timestamp_ms is None
        else Instant(
            datetime.fromtimestamp(record.timestamp_ms / 1000, UTC).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            )
        )
    )
    return SchedulerEventRecord(
        workspace_id,
        event_id,
        "stream.record",
        stream_id,
        record.key,
        digest,
        occurred,
        Instant(received_at),
    )


def _ingest_event(
    store: SchedulerEventStore, event: SchedulerEventRecord
) -> tuple[EventDelivery, ...]:
    get_event = getattr(store, "get_event", None)
    try:
        return store.ingest_event(event)
    except SchedulerEventConflict:
        if not callable(get_event):
            raise
        existing = get_event(event.workspace_id, event.id)
        if existing is None:
            raise
        if (
            existing.workspace_id,
            existing.id,
            existing.event_type,
            existing.source_ref,
            existing.subject_ref,
            existing.payload_digest,
            existing.occurred_at,
        ) != (
            event.workspace_id,
            event.id,
            event.event_type,
            event.source_ref,
            event.subject_ref,
            event.payload_digest,
            event.occurred_at,
        ):
            raise
        return store.ingest_event(existing)
