from pathlib import Path

import pytest
from studio_core import AssetId, CatalogAsset, OwnershipMetadata, Workspace, WorkspaceId
from studio_orchestrator import Instant
from studio_storage.catalog import CatalogConflict, SqliteCatalogStore
from studio_storage.workspaces import SqliteWorkspaceStore


def test_catalog_ownership_is_versioned_and_idempotent(tmp_path: Path) -> None:
    now = Instant("2026-09-13T10:10:00.000000Z")
    workspace = WorkspaceId("workspace-ownership")
    database = tmp_path / "catalog.sqlite3"
    SqliteWorkspaceStore(database, migration_now=now).create_workspace(
        Workspace(workspace, "Ownership workspace"), now=now
    )
    catalog = SqliteCatalogStore(database, migration_now=now)
    asset_id = AssetId("asset/orders")
    catalog.create_asset(workspace, CatalogAsset(asset_id, "table", "Orders"), now=now)
    first = OwnershipMetadata(1, "group/data", ("user/steward",), "sales", "active")
    second = OwnershipMetadata(2, "group/platform", (), "sales", "deprecated")
    assert catalog.put_ownership(workspace, asset_id, first, now=now) == first
    assert catalog.put_ownership(workspace, asset_id, first, now=now) == first
    assert catalog.put_ownership(workspace, asset_id, second, now=now) == second
    assert catalog.get_ownership(workspace, asset_id) == second
    assert catalog.list_ownership_versions(workspace, asset_id) == (first, second)
    with pytest.raises(CatalogConflict):
        catalog.put_ownership(
            workspace,
            asset_id,
            OwnershipMetadata(1, "group/other"),
            now=now,
        )
