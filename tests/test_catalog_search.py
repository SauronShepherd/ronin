from pathlib import Path

import pytest
from studio_core import (
    AssetId,
    AssetRef,
    AssetRevision,
    AssetVersion,
    CatalogAsset,
    LineageEdge,
    SensitivityMetadata,
    Workspace,
    WorkspaceId,
)
from studio_orchestrator import Instant
from studio_storage.catalog import CatalogConflict, SqliteCatalogStore
from studio_storage.workspaces import SqliteWorkspaceStore


def test_catalog_search_is_project_scoped_and_matches_governance_metadata(tmp_path: Path) -> None:
    now = Instant("2026-09-13T10:10:00.000000Z")
    workspace = WorkspaceId("workspace-search")
    database = tmp_path / "catalog.sqlite3"
    SqliteWorkspaceStore(database, migration_now=now).create_workspace(
        Workspace(workspace, "Search workspace"), now=now
    )
    catalog = SqliteCatalogStore(database, migration_now=now)
    catalog.create_asset(
        workspace,
        CatalogAsset(
            AssetId("asset/orders"),
            "table",
            "Orders",
            tags=("curated",),
            classifications=("pii",),
        ),
        now=now,
    )

    assert tuple(asset.id for asset in catalog.search_assets(workspace, "PII")) == (
        AssetId("asset/orders"),
    )
    assert catalog.search_assets(workspace, "missing") == ()
    with pytest.raises(ValueError, match="must not be empty"):
        catalog.search_assets(workspace, " ")
    with pytest.raises(ValueError, match="between 1 and 1000"):
        catalog.search_assets(workspace, "orders", limit=0)


def test_catalog_sensitivity_is_versioned_idempotent_and_latest_is_effective(
    tmp_path: Path,
) -> None:
    now = Instant("2026-09-13T10:10:00.000000Z")
    workspace = WorkspaceId("workspace-sensitivity")
    database = tmp_path / "catalog.sqlite3"
    SqliteWorkspaceStore(database, migration_now=now).create_workspace(
        Workspace(workspace, "Sensitivity workspace"), now=now
    )
    catalog = SqliteCatalogStore(database, migration_now=now)
    asset_id = AssetId("asset/customers")
    catalog.create_asset(workspace, CatalogAsset(asset_id, "table", "Customers"), now=now)
    first = SensitivityMetadata(1, explicit=("pii",), inherited=("internal",))
    second = SensitivityMetadata(2, explicit=("restricted",), inherited=("pii",))
    assert catalog.put_sensitivity(workspace, asset_id, first, now=now) == first
    assert catalog.put_sensitivity(workspace, asset_id, first, now=now) == first
    assert catalog.put_sensitivity(workspace, asset_id, second, now=now) == second
    assert catalog.get_sensitivity(workspace, asset_id) == second
    assert catalog.list_sensitivity_versions(workspace, asset_id) == (first, second)
    with pytest.raises(CatalogConflict, match="already exists"):
        catalog.put_sensitivity(
            workspace,
            asset_id,
            SensitivityMetadata(1, explicit=("restricted",)),
            now=now,
        )


def test_catalog_lineage_listing_is_deterministic_and_bounded(tmp_path: Path) -> None:
    now = Instant("2026-09-13T10:10:00.000000Z")
    workspace = WorkspaceId("workspace-lineage")
    database = tmp_path / "catalog.sqlite3"
    SqliteWorkspaceStore(database, migration_now=now).create_workspace(
        Workspace(workspace, "Lineage workspace"), now=now
    )
    catalog = SqliteCatalogStore(database, migration_now=now)
    for asset_id in ("source", "target", "other"):
        catalog.create_asset(workspace, CatalogAsset(AssetId(asset_id), "table", asset_id), now=now)
    source = AssetRef(AssetId("source"), AssetVersion("1"))
    target = AssetRef(AssetId("target"), AssetVersion("1"))
    other = AssetRef(AssetId("other"), AssetVersion("1"))
    for ref in (source, target, other):
        catalog.put_revision(workspace, AssetRevision(ref), now=now)
    first = LineageEdge(source, target, "transform", "declared")
    second = LineageEdge(other, target, "read", "observed")
    catalog.put_lineage(workspace, second, now=now)
    catalog.put_lineage(workspace, first, now=now)
    listed = catalog.list_lineage(workspace)
    assert tuple(edge.digest for edge in listed) == tuple(sorted((first.digest, second.digest)))
    assert catalog.list_lineage(workspace, limit=1) == listed[:1]
    with pytest.raises(ValueError, match="between 1 and 10000"):
        catalog.list_lineage(workspace, limit=0)
