import pytest

from studio_core import AssetId, AssetRef, AssetVersion, LineageEdge
from studio_data_engineering import publish_lineage_event, record_pipeline_lineage
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
