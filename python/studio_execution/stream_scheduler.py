"""Adapter from streaming records to the durable scheduler event inbox."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from studio_core import WorkspaceId
from studio_core.scheduler_events import SchedulerEventId
from studio_orchestrator import Instant
from studio_storage.scheduler_events import EventDelivery, SchedulerEventRecord, SchedulerEventStore
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
    return store.ingest_event(
        SchedulerEventRecord(
            workspace_id,
            event_id,
            "stream.record",
            stream_id,
            record.key,
            digest,
            occurred,
            Instant(received_at),
        )
    )
