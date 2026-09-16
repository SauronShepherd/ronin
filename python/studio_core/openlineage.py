"""Dependency-free OpenLineage-compatible payload generation."""

from __future__ import annotations

from typing import TypeAlias

from .catalog import LineageEdge

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


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
    if not namespace or namespace != namespace.strip() or "\n" in namespace or "\r" in namespace:
        raise ValueError("namespace must be non-empty and single-line")
    if not event_time or event_time != event_time.strip() or not event_time.endswith("Z"):
        raise ValueError("event_time must be a non-empty UTC timestamp ending in Z")
    timestamp = event_time
    run_id = edge.execution_ref or edge.digest
    event: dict[str, JsonValue] = {
        "eventType": "COMPLETE" if edge.mode == "observed" else "OTHER",
        "eventTime": timestamp,
        "run": {"runId": run_id, "facets": {"ronin_lineage": {"mode": edge.mode}}},
        "job": {"namespace": namespace, "name": job_name or edge.operation},
        "inputs": [
            {
                "namespace": namespace,
                "name": f"{edge.source.asset_id.value}@{edge.source.version.value}",
            }
        ],
        "outputs": [
            {
                "namespace": namespace,
                "name": f"{edge.target.asset_id.value}@{edge.target.version.value}",
            }
        ],
        "producer": "ronin",
    }
    if edge.column_mappings:
        event["columnLineage"] = {
            "fields": {
                mapping.target_field: {
                    "inputFields": [
                        {"namespace": namespace, "name": field} for field in mapping.source_fields
                    ]
                }
                for mapping in edge.column_mappings
            }
        }
    return event


__all__ = ["lineage_event_payload"]
