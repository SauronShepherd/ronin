from studio_core.catalog import AssetId, AssetRef, AssetVersion, ColumnMapping, LineageEdge
from studio_core.openlineage import lineage_event_payload


def test_lineage_event_is_standard_shaped_and_deterministic() -> None:
    edge = LineageEdge(
        source=AssetRef(AssetId("orders"), AssetVersion("v1")),
        target=AssetRef(AssetId("daily_orders"), AssetVersion("v2")),
        operation="transform", mode="observed", execution_ref="run-42",
        column_mappings=(ColumnMapping("total", ("amount",)),),
    )
    event = lineage_event_payload(edge, namespace="workspace", job_name="daily-orders",
                                  event_time="2026-09-15T12:00:00Z")
    assert event["eventType"] == "COMPLETE"
    assert event["eventTime"] == "2026-09-15T12:00:00Z"
    assert event["run"] == {"runId": "run-42", "facets": {"ronin_lineage": {"mode": "observed"}}}
    assert event["inputs"] == [{"namespace": "workspace", "name": "orders@v1"}]
    assert event["columnLineage"] == {"fields": {"total": {"inputFields": [{"namespace": "workspace", "name": "amount"}]}}}


def test_declared_edge_uses_other_event_and_digest_run_id() -> None:
    edge = LineageEdge(source=AssetRef(AssetId("a"), AssetVersion("1")),
                       target=AssetRef(AssetId("b"), AssetVersion("1")),
                       operation="write", mode="declared")
    event = lineage_event_payload(edge, namespace="n", event_time="2026-01-01T00:00:00Z")
    assert event["eventType"] == "OTHER"
    assert event["run"]["runId"] == edge.digest
