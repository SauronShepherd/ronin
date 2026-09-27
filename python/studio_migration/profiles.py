"""Named vendor discovery profiles backed by the canonical inventory kernel."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from studio_core.portability import MigrationReport

from .inventory import inventory_json_document


def _discover(
    document: str | bytes,
    *,
    platform: str,
    source_version: str,
    importer_version: str,
) -> MigrationReport:
    return inventory_json_document(
        document,
        source_platform=platform,
        source_version=source_version,
        importer_version=importer_version,
    )


def _normalize(document: str | bytes, collections: tuple[str, ...]) -> str:
    """Normalize common vendor export collection shapes without dropping objects."""
    try:
        payload = json.loads(document)
    except (TypeError, ValueError) as exc:
        raise ValueError("vendor export is not valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("vendor export root must be an object")
    nested = payload.get("resources")
    if isinstance(nested, Mapping):
        payload = {**payload, **nested}
    if isinstance(payload.get("objects"), Sequence) and not isinstance(
        payload["objects"], (str, bytes)
    ):
        return json.dumps(payload, separators=(",", ":"))
    objects: list[dict[str, object]] = []
    for collection in collections:
        values = payload.get(collection, ())
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            continue
        for ordinal, value in enumerate(values):
            if not isinstance(value, Mapping):
                raise ValueError(f"vendor collection {collection} contains a non-object")
            identity = value.get("id", value.get("name"))
            if not isinstance(identity, str) or not identity.strip():
                raise ValueError(
                    f"vendor collection {collection} object {ordinal} has no explicit identity"
                )
            objects.append(
                {
                    "type": collection[:-1] if collection.endswith("s") else collection,
                    "id": identity,
                }
            )
    if not objects:
        identity = payload.get("id", payload.get("job_id", payload.get("project_id")))
        if isinstance(identity, str) and identity.strip():
            objects.append({"type": "export", "id": identity})
    return json.dumps({"objects": objects}, separators=(",", ":"))


def discover_databricks(
    document: str | bytes, *, source_version: str = "unknown"
) -> MigrationReport:
    return _discover(
        _normalize(
            document, ("jobs", "pipelines", "clusters", "notebooks", "models", "dashboards")
        ),
        platform="databricks",
        source_version=source_version,
        importer_version="ronin-databricks-0.1",
    )


def discover_fabric(document: str | bytes, *, source_version: str = "unknown") -> MigrationReport:
    return _discover(
        _normalize(
            document, ("items", "notebooks", "pipelines", "lakehouses", "warehouses", "reports")
        ),
        platform="microsoft-fabric",
        source_version=source_version,
        importer_version="ronin-fabric-0.1",
    )


def discover_dataiku(document: str | bytes, *, source_version: str = "unknown") -> MigrationReport:
    return _discover(
        _normalize(
            document, ("datasets", "recipes", "scenarios", "notebooks", "models", "connections")
        ),
        platform="dataiku-dss",
        source_version=source_version,
        importer_version="ronin-dataiku-0.1",
    )


def discover_foundry(document: str | bytes, *, source_version: str = "unknown") -> MigrationReport:
    return _discover(
        _normalize(
            document, ("datasets", "objectTypes", "linkTypes", "actions", "pipelines", "functions")
        ),
        platform="palantir-foundry-aip",
        source_version=source_version,
        importer_version="ronin-foundry-0.1",
    )


__all__ = ("discover_databricks", "discover_fabric", "discover_dataiku", "discover_foundry")
