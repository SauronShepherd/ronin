from typing import cast

from studio_core import WorkspaceId
from studio_execution.stream_scheduler import ingest_stream_record
from studio_orchestrator import Instant
from studio_storage.scheduler_events import EventDelivery, SchedulerEventStore
from studio_streaming import StreamRecord


class _Inbox:
    def __init__(self) -> None:
        self.record = None

    def ingest_event(self, record):
        self.record = record
        return ()


def test_stream_scheduler_bridge_is_deterministic() -> None:
    inbox = _Inbox()
    result = ingest_stream_record(
        cast(SchedulerEventStore, inbox),
        StreamRecord(2, 7, 1_000, "key", {"value": 1}),
        workspace_id=WorkspaceId("ws"), stream_id="events",
        received_at=Instant("2026-09-15T00:00:00.000000Z"),
    )
    assert result == ()
    assert inbox.record.id.value == "stream-events-2-7"
    assert str(inbox.record.occurred_at) == "1970-01-01T00:00:01.000000Z"
