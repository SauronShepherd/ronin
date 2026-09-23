from pathlib import Path

import pytest
from studio_data_engineering import (
    CompilationReport,
    SqliteCompilationStore,
    publish_pending_compilation_events,
)


def test_compilation_report_survives_reopen(tmp_path: Path) -> None:
    store = SqliteCompilationStore(tmp_path / "ronin.db")
    report = CompilationReport("local-preview", True, (), 2, 1)
    store.save_report(revision_key="p/main/1", ir_digest="ir-1", report=report)
    reopened = SqliteCompilationStore(tmp_path / "ronin.db")
    found = reopened.get_report(revision_key="p/main/1", runtime="local-preview", ir_digest="ir-1")
    assert found is not None
    assert found["portable"] is True
    assert found["node_count"] == 2


def test_outbox_is_idempotent_and_publishable(tmp_path: Path) -> None:
    store = SqliteCompilationStore(tmp_path / "ronin.db")
    event = {
        "event_id": "event-1",
        "event_type": "data-engineering.compilation-completed.v1",
        "aggregate_key": "p/main/1",
        "payload": {"portable": True},
    }
    assert store.enqueue(**event) is True
    assert store.enqueue(**event) is False
    assert len(store.pending_events()) == 1
    assert store.mark_published("event-1") is True
    assert store.mark_published("event-1") is False
    assert store.pending_events() == ()


def test_latest_report_query_returns_ir_digest(tmp_path: Path) -> None:
    store = SqliteCompilationStore(tmp_path / "ronin.db")
    store.save_report(
        revision_key="p/main/1",
        ir_digest="ir-1",
        report=CompilationReport("spark-connect", False, (), 1, 0),
    )
    found = store.get_latest_report(revision_key="p/main/1", runtime="spark-connect")
    assert found is not None
    assert found["ir_digest"] == "ir-1"


@pytest.mark.asyncio
async def test_outbox_publisher_acknowledges_only_after_transport_success(tmp_path: Path) -> None:
    store = SqliteCompilationStore(tmp_path / "ronin.db")
    store.enqueue(
        event_id="event-1",
        event_type="data-engineering.compilation-completed.v1",
        aggregate_key="p/main/1",
        payload={"portable": True},
    )
    delivered: list[str] = []

    async def publish(event):
        delivered.append(str(event["event_id"]))

    assert await publish_pending_compilation_events(store, publish) == ("event-1",)
    assert delivered == ["event-1"]
    assert store.pending_events() == ()


@pytest.mark.asyncio
async def test_outbox_publisher_leaves_event_pending_on_failure(tmp_path: Path) -> None:
    store = SqliteCompilationStore(tmp_path / "ronin.db")
    store.enqueue(
        event_id="event-2",
        event_type="data-engineering.compilation-completed.v1",
        aggregate_key="p/main/1",
        payload={"portable": False},
    )

    async def publish(_event):
        raise RuntimeError("transport unavailable")

    with pytest.raises(RuntimeError, match="transport unavailable"):
        await publish_pending_compilation_events(store, publish)
    assert [item["event_id"] for item in store.pending_events()] == ["event-2"]
