import pytest
from studio_core.catalog import AssetId, AssetRef, AssetVersion, ColumnMapping, LineageEdge
from studio_core.openlineage import (
    OPENLINEAGE_COLUMN_LINEAGE_SCHEMA,
    OPENLINEAGE_PRODUCER,
    OPENLINEAGE_RUN_EVENT_SCHEMA,
    lineage_event_payload,
)
from studio_core.openlineage_transport import validate_openlineage_event


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
    assert event["run"] == {"runId": "run-42"}
    assert event["job"] == {"namespace": "workspace", "name": "daily-orders"}
    assert event["inputs"] == [{"namespace": "workspace", "name": "orders@v1"}]
    assert event["producer"] == OPENLINEAGE_PRODUCER
    assert event["schemaURL"] == OPENLINEAGE_RUN_EVENT_SCHEMA
    validate_openlineage_event(event)
    assert event["outputs"] == [
        {
            "namespace": "workspace",
            "name": "daily_orders@v2",
            "facets": {
                "columnLineage": {
                    "_producer": OPENLINEAGE_PRODUCER,
                    "_schemaURL": OPENLINEAGE_COLUMN_LINEAGE_SCHEMA,
                    "fields": {
                        "total": {
                            "inputFields": [
                                {
                                    "namespace": "workspace",
                                    "name": "orders@v1",
                                    "field": "amount",
                                }
                            ]
                        }
                    },
                }
            },
        }
    ]


def test_declared_edge_uses_dataset_event_and_lineage_facet() -> None:
    edge = LineageEdge(
        source=AssetRef(AssetId("a"), AssetVersion("1")),
        target=AssetRef(AssetId("b"), AssetVersion("1")),
        operation="write",
        mode="declared",
    )
    event = lineage_event_payload(edge, namespace="n", event_time="2026-01-01T00:00:00Z")
    assert "eventType" not in event
    assert (
        event["schemaURL"]
        == "https://openlineage.io/spec/1-0-5/OpenLineage.json#/definitions/DatasetEvent"
    )
    assert event["dataset"]["facets"]["lineage"]["inputs"] == [
        {"namespace": "n", "name": "a@1", "type": "DATASET"}
    ]
    validate_openlineage_event(event)


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
    output = event["outputs"][0]
    assert output["facets"]["columnLineage"]["fields"] == {
        "total": {
            "inputFields": [
                {"namespace": "n", "name": "a@1", "field": "amount"},
                {"namespace": "n", "name": "a@1", "field": "tax"},
            ]
        },
        "customer": {"inputFields": [{"namespace": "n", "name": "a@1", "field": "customer_id"}]},
    }


@pytest.mark.parametrize(
    "namespace",
    ["", " workspace", "workspace ", "workspace\nline", "workspace\rline", "workspace\tline"],
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


@pytest.mark.parametrize(
    "event_time",
    ["", " 2026-01-01T00:00:00Z", "2026-01-01T00:00:00", "2026-01-01T00:00:00+01:00", "garbageZ"],
)
def test_lineage_event_rejects_invalid_event_time(event_time: str) -> None:
    edge = LineageEdge(
        source=AssetRef(AssetId("a"), AssetVersion("1")),
        target=AssetRef(AssetId("b"), AssetVersion("1")),
        operation="write",
        mode="declared",
    )
    with pytest.raises(
        ValueError,
        match="^event_time must be a valid UTC timestamp$",
    ):
        lineage_event_payload(edge, namespace="n", event_time=event_time)


@pytest.mark.parametrize("job_name", [" job", "job ", "job\tname"])
def test_observed_lineage_rejects_untrimmed_or_controlled_job_name(job_name: str) -> None:
    edge = LineageEdge(
        source=AssetRef(AssetId("a"), AssetVersion("1")),
        target=AssetRef(AssetId("b"), AssetVersion("1")),
        operation="transform",
        mode="observed",
        execution_ref="run-1",
    )
    with pytest.raises(ValueError, match="job_name"):
        lineage_event_payload(
            edge, namespace="n", job_name=job_name, event_time="2026-01-01T00:00:00Z"
        )


def test_declared_lineage_uses_dataset_event_and_ignores_run_job_name() -> None:
    edge = LineageEdge(
        source=AssetRef(AssetId("a"), AssetVersion("1")),
        target=AssetRef(AssetId("b"), AssetVersion("1")),
        operation="write",
        mode="declared",
    )
    event = lineage_event_payload(
        edge,
        namespace="n",
        job_name="",
        event_time="2026-01-01T00:00:00Z",
    )
    assert event["dataset"]["name"] == "b@1"
    assert "run" not in event
    assert "job" not in event
