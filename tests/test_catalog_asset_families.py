from pathlib import Path

import pytest
from studio_core import ASSET_KINDS, AssetId, CatalogAsset, Workspace, WorkspaceId
from studio_orchestrator import Instant
from studio_storage.catalog import SqliteCatalogStore
from studio_storage.workspaces import SqliteWorkspaceStore


@pytest.mark.parametrize("kind", sorted(ASSET_KINDS))
def test_every_declared_asset_family_round_trips_through_catalog(tmp_path: Path, kind: str) -> None:
    now = Instant("2026-09-13T10:10:00.000000Z")
    workspace = WorkspaceId(f"workspace-{kind}")
    database = tmp_path / "catalog.sqlite3"
    SqliteWorkspaceStore(database, migration_now=now).create_workspace(
        Workspace(workspace, "Asset family workspace"), now=now
    )
    catalog = SqliteCatalogStore(database, migration_now=now)
    asset = CatalogAsset(
        AssetId(f"asset/{kind}"),
        kind,
        f"Example {kind}",
        project_id="project/example",
        owner_ref="group/data",
        tags=("governed",),
        classifications=("internal",),
    )
    assert catalog.create_asset(workspace, asset, now=now) == asset
    assert catalog.get_asset(workspace, asset.id) == asset
    assert catalog.search_assets(workspace, kind) == (asset,)
