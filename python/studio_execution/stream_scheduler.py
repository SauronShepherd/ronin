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
    event = SchedulerEventRecord(
        workspace_id,
        event_id,
        "stream.record",
        stream_id,
        record.key,
        digest,
        occurred,
        Instant(received_at),
    )
    get_event = getattr(store, "get_event", None)
    if callable(get_event):
        existing = get_event(workspace_id, event_id)
        if existing is not None:
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
                return store.ingest_event(event)
            # A replay may be observed at a later wall-clock time. Reuse the
            # first receipt timestamp so the deterministic stream event stays
            # idempotent without weakening scheduler event conflict checks.
            return store.ingest_event(existing)
    try:
        return store.ingest_event(event)
    except SchedulerEventConflict:
        if not callable(get_event):
            raise
        existing = get_event(workspace_id, event_id)
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
