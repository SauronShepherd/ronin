from __future__ import annotations

import pytest
from studio_core.catalog import AssetId, AssetRef, AssetVersion, ColumnMapping, LineageEdge
from studio_core.openlineage import OPENLINEAGE_PRODUCER, lineage_event_payload


def _edge() -> LineageEdge:
    return LineageEdge(
        source=AssetRef(AssetId("source"), AssetVersion("v1")),
        target=AssetRef(AssetId("target"), AssetVersion("v2")),
        operation="transform",
        mode="observed",
        execution_ref="run-1",
        column_mappings=(ColumnMapping("total", ("amount", "tax")),),
    )


def test_openlineage_payload_preserves_all_standard_field_names_and_values() -> None:
    event = lineage_event_payload(
        _edge(), namespace="workspace", job_name="job", event_time="2026-01-01T00:00:00Z"
    )

    assert set(event) == {
        "eventType",
        "eventTime",
        "run",
        "job",
        "inputs",
        "outputs",
        "producer",
        "schemaURL",
    }
    assert event["outputs"][0]["name"] == "target@v2"
    assert event["producer"] == OPENLINEAGE_PRODUCER
    output = event["outputs"][0]
    assert output["facets"]["columnLineage"]["fields"] == {
        "total": {
            "inputFields": [
                {"namespace": "workspace", "name": "source@v1", "field": "amount"},
                {"namespace": "workspace", "name": "source@v1", "field": "tax"},
            ]
        }
    }


@pytest.mark.parametrize("namespace", ["line\nfeed", "carriage\rreturn"])
def test_openlineage_namespace_error_is_exact_for_each_control_character(namespace: str) -> None:
    with pytest.raises(ValueError, match=".") as error:
        lineage_event_payload(_edge(), namespace=namespace, event_time="2026-01-01T00:00:00Z")
    assert str(error.value) == "namespace must be non-empty and single-line"


def test_openlineage_event_time_error_is_exact() -> None:
    with pytest.raises(ValueError, match=".") as error:
        lineage_event_payload(_edge(), namespace="workspace", event_time="2026-01-01T00:00:00")
    assert str(error.value) == "event_time must be a valid UTC timestamp"
