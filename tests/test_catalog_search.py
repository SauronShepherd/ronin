from pathlib import Path

import pytest
from studio_core import AssetId, CatalogAsset, Workspace, WorkspaceId
from studio_orchestrator import Instant
from studio_storage.catalog import SqliteCatalogStore
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
