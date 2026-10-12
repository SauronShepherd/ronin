import pytest
from studio_core.catalog import AssetId, AssetRef, AssetVersion, ColumnMapping, LineageEdge
from studio_core.openlineage import lineage_event_payload


def test_lineage_event_is_standard_shaped_and_deterministic() -> None:
    edge = LineageEdge(
        source=AssetRef(AssetId("orders"), AssetVersion("v1")),
        target=AssetRef(AssetId("daily_orders"), AssetVersion("v2")),
        operation="transform",
        mode="observed",
        execution_ref="run-42",
        column_mappings=(ColumnMapping("total", ("amount",)),),
    )
    event = lineage_event_payload(
        edge, namespace="workspace", job_name="daily-orders", event_time="2026-09-15T12:00:00Z"
    )
    assert event["eventType"] == "COMPLETE"
    assert event["eventTime"] == "2026-09-15T12:00:00Z"
    assert event["run"] == {"runId": "run-42", "facets": {"ronin_lineage": {"mode": "observed"}}}
    assert event["job"] == {"namespace": "workspace", "name": "daily-orders"}
    assert event["inputs"] == [{"namespace": "workspace", "name": "orders@v1"}]
    assert event["outputs"] == [{"namespace": "workspace", "name": "daily_orders@v2"}]
    assert event["producer"] == "ronin"
    assert event["columnLineage"] == {
        "fields": {"total": {"inputFields": [{"namespace": "workspace", "name": "amount"}]}}
    }


def test_declared_edge_uses_other_event_and_digest_run_id() -> None:
    edge = LineageEdge(
        source=AssetRef(AssetId("a"), AssetVersion("1")),
        target=AssetRef(AssetId("b"), AssetVersion("1")),
        operation="write",
        mode="declared",
    )
    event = lineage_event_payload(edge, namespace="n", event_time="2026-01-01T00:00:00Z")
    assert event["eventType"] == "OTHER"
    assert event["run"]["runId"] == edge.digest


def test_lineage_event_defaults_job_to_operation_and_omits_empty_column_lineage() -> None:
    edge = LineageEdge(
        source=AssetRef(AssetId("a"), AssetVersion("1")),
        target=AssetRef(AssetId("b"), AssetVersion("1")),
        operation="write",
        mode="observed",
    )
    event = lineage_event_payload(edge, namespace="n", event_time="2026-01-01T00:00:00Z")
    assert event["job"] == {"namespace": "n", "name": "write"}
    assert "columnLineage" not in event


def test_lineage_event_renders_all_column_mapping_fields() -> None:
    edge = LineageEdge(
        source=AssetRef(AssetId("a"), AssetVersion("1")),
        target=AssetRef(AssetId("b"), AssetVersion("1")),
        operation="transform",
        mode="observed",
        column_mappings=(
            ColumnMapping("total", ("amount", "tax")),
            ColumnMapping("customer", ("customer_id",)),
        ),
    )
    event = lineage_event_payload(edge, namespace="n", event_time="2026-01-01T00:00:00Z")
    assert event["columnLineage"] == {
        "fields": {
            "total": {
                "inputFields": [
                    {"namespace": "n", "name": "amount"},
                    {"namespace": "n", "name": "tax"},
                ]
            },
            "customer": {"inputFields": [{"namespace": "n", "name": "customer_id"}]},
        }
    }


@pytest.mark.parametrize(
    "namespace", ["", " workspace", "workspace ", "workspace\nline", "workspace\rline"]
)
def test_lineage_event_rejects_invalid_namespace(namespace: str) -> None:
    edge = LineageEdge(
        source=AssetRef(AssetId("a"), AssetVersion("1")),
        target=AssetRef(AssetId("b"), AssetVersion("1")),
        operation="write",
        mode="declared",
    )
    with pytest.raises(ValueError, match="^namespace must be non-empty and single-line$"):
        lineage_event_payload(edge, namespace=namespace, event_time="2026-01-01T00:00:00Z")


@pytest.mark.parametrize("event_time", ["", " 2026-01-01T00:00:00Z", "2026-01-01T00:00:00"])
def test_lineage_event_rejects_invalid_event_time(event_time: str) -> None:
    edge = LineageEdge(
        source=AssetRef(AssetId("a"), AssetVersion("1")),
        target=AssetRef(AssetId("b"), AssetVersion("1")),
        operation="write",
        mode="declared",
    )
    with pytest.raises(
        ValueError,
        match="^event_time must be a non-empty UTC timestamp ending in Z$",
    ):
        lineage_event_payload(edge, namespace="n", event_time=event_time)
