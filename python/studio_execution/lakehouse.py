"""Governed open-data-plane application services."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from studio_core import (
    AssetId,
    AssetRef,
    AssetRevision,
    AssetVersion,
    CatalogAsset,
    LineageEdge,
    WorkspaceId,
)
from studio_core.canonical_json import encode as encode_canonical_json
from studio_lakehouse import ParquetFile, write_parquet_rows
from studio_storage.ports import CatalogStore


class GovernedDataConflict(RuntimeError):
    """Raised when stable governed identity conflicts with existing catalog intent."""


@dataclass(frozen=True, slots=True)
class GovernedParquetWrite:
    file: ParquetFile
    asset: CatalogAsset
    revision: AssetRevision
    lineage: LineageEdge | None


def _schema_digest(file: ParquetFile) -> str:
    payload = [
        {"name": field.name, "type": field.type_name, "nullable": field.nullable}
        for field in file.schema
    ]
    return hashlib.sha256(encode_canonical_json(payload)).hexdigest()


def write_governed_parquet(
    catalog: CatalogStore,
    workspace_id: WorkspaceId,
    *,
    asset_id: AssetId,
    name: str,
    path: Path,
    rows: Iterable[Mapping[str, object]],
    project_id: str | None = None,
    source: AssetRef | None = None,
    execution_ref: str | None = None,
    now: str,
) -> GovernedParquetWrite:
    """Write one Parquet file and commit content-addressed catalog/lineage metadata."""

    file = write_parquet_rows(path, rows)
    expected_asset = CatalogAsset(
        asset_id,
        "file",
        name,
        project_id=project_id,
        properties=(("format", "parquet"),),
    )
    existing = catalog.get_asset(workspace_id, asset_id)
    if existing is None:
        asset = catalog.create_asset(workspace_id, expected_asset, now=now)
    elif existing == expected_asset:
        asset = existing
    else:
        raise GovernedDataConflict(
            f"asset id already exists with different governed identity: {asset_id}"
        )

    revision = AssetRevision(
        AssetRef(asset_id, AssetVersion(file.sha256)),
        schema_digest=_schema_digest(file),
        content_digest=file.sha256,
        metadata=(
            ("bytes", str(file.bytes)),
            ("format", "parquet"),
            ("locator", file.path.as_uri()),
            ("rows", str(file.rows)),
        ),
    )
    revision = catalog.put_revision(workspace_id, revision, now=now)

    lineage: LineageEdge | None = None
    if source is not None:
        lineage = catalog.put_lineage(
            workspace_id,
            LineageEdge(
                source,
                revision.ref,
                "transform",
                "observed",
                execution_ref=execution_ref,
            ),
            now=now,
        )
    return GovernedParquetWrite(file, asset, revision, lineage)


__all__ = (
    "GovernedDataConflict",
    "GovernedParquetWrite",
    "write_governed_parquet",
)
