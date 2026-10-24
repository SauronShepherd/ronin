"""Dependency-free OpenLineage-compatible payload generation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypeAlias

from .catalog import LineageEdge

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]

OPENLINEAGE_PRODUCER = "https://github.com/SauronShepherd/ronin"
OPENLINEAGE_RUN_EVENT_SCHEMA = (
    "https://openlineage.io/spec/1-0-5/OpenLineage.json#/definitions/RunEvent"
)
OPENLINEAGE_DATASET_EVENT_SCHEMA = (
    "https://openlineage.io/spec/1-0-5/OpenLineage.json#/definitions/DatasetEvent"
)
OPENLINEAGE_COLUMN_LINEAGE_SCHEMA = (
    "https://openlineage.io/spec/facets/1-2-0/ColumnLineageDatasetFacet.json"
)
OPENLINEAGE_LINEAGE_FACET_SCHEMA = (
    "https://openlineage.io/spec/facets/1-0-0/LineageFacet.json#/$defs/LineageDatasetFacet"
)


def lineage_event_payload(
    edge: LineageEdge,
    *,
    namespace: str,
    job_name: str | None = None,
    event_time: str,
) -> dict[str, JsonValue]:
    """Render one committed edge as a deterministic OpenLineage-style event.

    This is an export boundary only: transport, authentication, and server-side
    schema validation remain deployment concerns.
    """
    if (
        not namespace
        or namespace != namespace.strip()
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in namespace)
    ):
        raise ValueError("namespace must be non-empty and single-line")
    try:
        parsed_event_time = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("event_time must be a valid UTC timestamp") from exc
    if (
        not event_time
        or event_time != event_time.strip()
        or parsed_event_time.tzinfo is None
        or parsed_event_time.utcoffset() != UTC.utcoffset(parsed_event_time)
    ):
        raise ValueError("event_time must be a valid UTC timestamp")
    timestamp = event_time
    source_name = f"{edge.source.asset_id.value}@{edge.source.version.value}"
    target_name = f"{edge.target.asset_id.value}@{edge.target.version.value}"
    if edge.mode == "declared":
        lineage_facet: dict[str, JsonValue] = {
            "_producer": OPENLINEAGE_PRODUCER,
            "_schemaURL": OPENLINEAGE_LINEAGE_FACET_SCHEMA,
            "inputs": [{"namespace": namespace, "name": source_name, "type": "DATASET"}],
        }
        if edge.column_mappings:
            lineage_facet["fields"] = {
                mapping.target_field: {
                    "inputs": [
                        {
                            "namespace": namespace,
                            "name": source_name,
                            "type": "DATASET",
                            "field": source_field,
                        }
                        for source_field in mapping.source_fields
                    ]
                }
                for mapping in edge.column_mappings
            }
        return {
            "eventTime": timestamp,
            "dataset": {
                "namespace": namespace,
                "name": target_name,
                "facets": {"lineage": lineage_facet},
            },
            "producer": OPENLINEAGE_PRODUCER,
            "schemaURL": OPENLINEAGE_DATASET_EVENT_SCHEMA,
        }

    if job_name and (
        not job_name.strip()
        or job_name != job_name.strip()
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in job_name)
    ):
        raise ValueError("job_name must be non-empty and trimmed when provided")
    run_id = edge.execution_ref or edge.digest
    event: dict[str, JsonValue] = {
        "eventType": "COMPLETE",
        "eventTime": timestamp,
        "run": {"runId": run_id},
        "job": {"namespace": namespace, "name": job_name or edge.operation},
        "inputs": [{"namespace": namespace, "name": source_name}],
        "outputs": [{"namespace": namespace, "name": target_name}],
        "producer": OPENLINEAGE_PRODUCER,
        "schemaURL": OPENLINEAGE_RUN_EVENT_SCHEMA,
    }
    if edge.column_mappings:
        event["outputs"] = [
            {
                "namespace": namespace,
                "name": target_name,
                "facets": {
                    "columnLineage": {
                        "_producer": OPENLINEAGE_PRODUCER,
                        "_schemaURL": OPENLINEAGE_COLUMN_LINEAGE_SCHEMA,
                        "fields": {
                            mapping.target_field: {
                                "inputFields": [
                                    {
                                        "namespace": namespace,
                                        "name": source_name,
                                        "field": source_field,
                                    }
                                    for source_field in mapping.source_fields
                                ]
                            }
                            for mapping in edge.column_mappings
                        },
                    }
                },
            }
        ]
    return event


__all__ = [
    "OPENLINEAGE_COLUMN_LINEAGE_SCHEMA",
    "OPENLINEAGE_DATASET_EVENT_SCHEMA",
    "OPENLINEAGE_LINEAGE_FACET_SCHEMA",
    "OPENLINEAGE_PRODUCER",
    "OPENLINEAGE_RUN_EVENT_SCHEMA",
    "lineage_event_payload",
]
