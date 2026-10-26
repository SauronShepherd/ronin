from pathlib import Path
from typing import cast

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


def test_outbox_filters_multiple_event_types_with_a_shared_limit(tmp_path: Path) -> None:
    store = SqliteCompilationStore(tmp_path / "ronin.db")
    for event_id, event_type in (
        ("event-a", "lineage.run.v1"),
        ("event-b", "lineage.dataset.v1"),
        ("event-c", "unrelated.v1"),
    ):
        store.enqueue(
            event_id=event_id,
            event_type=event_type,
            aggregate_key="aggregate",
            payload={"id": event_id},
        )

    pending = store.pending_events(limit=1, event_type=("lineage.run.v1", "lineage.dataset.v1"))
    assert len(pending) == 1
    assert pending[0]["event_id"] == "event-a"
    assert store.pending_events(event_type=("lineage.dataset.v1",))[0]["event_id"] == "event-b"


def test_outbox_pending_queries_use_bounded_lookup_indexes(tmp_path: Path) -> None:
    store = SqliteCompilationStore(tmp_path / "ronin.db")
    connection = store._connect()
    try:
        unfiltered = connection.execute(
            "EXPLAIN QUERY PLAN SELECT event_id,event_type,aggregate_key,payload_json "
            "FROM de_outbox WHERE published_at IS NULL "
            "ORDER BY created_at,event_id LIMIT ?",
            (100,),
        ).fetchall()
        filtered = connection.execute(
            "EXPLAIN QUERY PLAN SELECT event_id,event_type,aggregate_key,payload_json "
            "FROM de_outbox WHERE published_at IS NULL AND event_type=? "
            "ORDER BY created_at,event_id LIMIT ?",
            ("openlineage.run-event.v1", 100),
        ).fetchall()
    finally:
        connection.close()

    assert any("de_outbox_pending_order_idx" in str(row[3]) for row in unfiltered)
    assert any("de_outbox_pending_type_idx" in str(row[3]) for row in filtered)


@pytest.mark.parametrize(
    "event_types",
    [
        (),
        ("lineage.run.v1", "lineage.run.v1"),
        ("lineage.run.v1", " "),
        cast(tuple[str, ...], (1,)),
        tuple(f"event-{index}" for index in range(17)),
    ],
)
def test_outbox_rejects_invalid_event_type_filters(tmp_path: Path, event_types) -> None:
    store = SqliteCompilationStore(tmp_path / "ronin.db")
    with pytest.raises(ValueError, match="event type filters"):
        store.pending_events(event_type=event_types)


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
