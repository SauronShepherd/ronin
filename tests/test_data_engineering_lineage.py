import pytest
from studio_core import AssetId, AssetRef, AssetVersion, LineageEdge
from studio_data_engineering import (
    SqliteCompilationStore,
    publish_lineage_event,
    publish_pending_lineage_events,
    record_pipeline_lineage,
    record_pipeline_lineage_and_enqueue,
)
from studio_orchestrator import Instant


class FakeCatalog:
    def __init__(self) -> None:
        self.items = []

    def put_lineage(self, workspace_id, edge, *, now):
        self.items.append((workspace_id, edge, now))
        return edge


def test_record_pipeline_lineage_uses_governed_catalog_contract() -> None:
    catalog = FakeCatalog()
    edge = record_pipeline_lineage(
        catalog,
        workspace_id="workspace-1",
        source=AssetRef(AssetId("raw/orders"), AssetVersion("1")),
        target=AssetRef(AssetId("curated/orders"), AssetVersion("1")),
        operation="transform",
        execution_ref="run-1",
        now=Instant("2026-09-19T10:00:00.000000Z"),
    )
    assert isinstance(edge, LineageEdge)
    assert edge.mode == "observed"
    assert edge.execution_ref == "run-1"
    assert len(catalog.items) == 1


@pytest.mark.asyncio
async def test_publish_lineage_event_emits_openlineage_payload() -> None:
    edge = LineageEdge(
        AssetRef(AssetId("raw/orders"), AssetVersion("1")),
        AssetRef(AssetId("curated/orders"), AssetVersion("1")),
        operation="transform",
        mode="observed",
        execution_ref="run-1",
    )
    delivered = []

    async def publish(event):
        delivered.append(event)

    await publish_lineage_event(
        edge,
        publish,
        namespace="workspace-1",
        event_time="2026-09-19T10:00:00Z",
        job_name="orders-pipeline",
    )
    assert delivered[0]["eventType"] == "COMPLETE"
    assert delivered[0]["run"]["runId"] == "run-1"


@pytest.mark.asyncio
async def test_lineage_outbox_is_durable_idempotent_and_acknowledged_after_delivery(
    tmp_path,
) -> None:
    catalog = FakeCatalog()
    outbox_path = tmp_path / "lineage-outbox.sqlite3"
    outbox = SqliteCompilationStore(outbox_path)
    parameters = {
        "workspace_id": "workspace-1",
        "source": AssetRef(AssetId("raw/orders"), AssetVersion("1")),
        "target": AssetRef(AssetId("curated/orders"), AssetVersion("1")),
        "operation": "transform",
        "execution_ref": "run-lineage-1",
        "now": Instant("2026-09-19T10:00:00.000000Z"),
        "namespace": "workspace-1",
        "event_time": "2026-09-19T10:00:00Z",
        "job_name": "orders-pipeline",
    }

    edge, event_id = record_pipeline_lineage_and_enqueue(catalog, outbox, **parameters)
    reopened = SqliteCompilationStore(outbox_path)
    pending = reopened.pending_events(event_type=("openlineage.run-event.v1",))
    assert len(pending) == 1
    assert pending[0]["event_id"] == event_id
    assert pending[0]["payload"]["run"]["runId"] == "run-lineage-1"

    replay_edge, replay_event_id = record_pipeline_lineage_and_enqueue(
        catalog, reopened, **parameters
    )
    assert replay_edge == edge
    assert replay_event_id == event_id
    assert len(reopened.pending_events(event_type="openlineage.run-event.v1")) == 1

    delivered = []

    async def publish(payload):
        delivered.append(payload)

    assert await publish_pending_lineage_events(reopened, publish) == (event_id,)
    assert delivered[0]["run"]["runId"] == "run-lineage-1"
    assert (
        reopened.pending_events(
            event_type=("openlineage.run-event.v1", "openlineage.dataset-event.v1")
        )
        == ()
    )


@pytest.mark.asyncio
async def test_failed_lineage_delivery_keeps_event_pending(tmp_path) -> None:
    outbox = SqliteCompilationStore(tmp_path / "lineage-outbox.sqlite3")
    edge = LineageEdge(
        AssetRef(AssetId("raw/orders"), AssetVersion("1")),
        AssetRef(AssetId("curated/orders"), AssetVersion("1")),
        operation="transform",
        mode="observed",
        execution_ref="run-lineage-fail",
    )
    event_id = record_pipeline_lineage_and_enqueue(
        FakeCatalog(),
        outbox,
        workspace_id="workspace-1",
        source=edge.source,
        target=edge.target,
        operation="transform",
        execution_ref="run-lineage-fail",
        now=Instant("2026-09-19T10:00:00.000000Z"),
        namespace="workspace-1",
        event_time="2026-09-19T10:00:00Z",
    )[1]

    async def fail(_payload):
        raise RuntimeError("collector unavailable")

    with pytest.raises(RuntimeError, match="collector unavailable"):
        await publish_pending_lineage_events(outbox, fail)
    assert [
        item["event_id"] for item in outbox.pending_events(event_type="openlineage.run-event.v1")
    ] == [event_id]
