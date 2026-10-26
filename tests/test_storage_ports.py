from __future__ import annotations

from pathlib import Path

import pytest
from studio_core import (
    AssetId,
    AssetRef,
    AssetRevision,
    AssetVersion,
    CatalogAsset,
    LineageEdge,
    Workspace,
    WorkspaceId,
)
from studio_storage import (
    ArtifactStore,
    CatalogStore,
    ConnectionStore,
    LocalArtifactStore,
    SqliteCatalogStore,
    SqliteConnectionStore,
    SqliteWorkspaceStore,
    WorkspaceStore,
)

NOW = "2026-09-12T20:00:00.000000Z"


def test_local_artifact_store_satisfies_artifact_port(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    assert isinstance(store, ArtifactStore)


def test_sqlite_workspace_store_satisfies_workspace_port(tmp_path: Path) -> None:
    store = SqliteWorkspaceStore(tmp_path / "ronin.db", migration_now=NOW)
    assert isinstance(store, WorkspaceStore)


def test_sqlite_connection_store_satisfies_connection_port(tmp_path: Path) -> None:
    store = SqliteConnectionStore(tmp_path / "ronin.db", migration_now=NOW)
    assert isinstance(store, ConnectionStore)


def test_sqlite_catalog_store_satisfies_catalog_port(tmp_path: Path) -> None:
    store = SqliteCatalogStore(tmp_path / "ronin.db", migration_now=NOW)
    assert isinstance(store, CatalogStore)


def test_sqlite_catalog_lists_every_asset_revision(tmp_path: Path) -> None:
    workspaces = SqliteWorkspaceStore(tmp_path / "ronin.db", migration_now=NOW)
    catalog = SqliteCatalogStore(tmp_path / "ronin.db", migration_now=NOW)
    workspace_id = WorkspaceId("retention-ws")
    workspaces.create_workspace(Workspace(workspace_id, "Retention"), now=NOW)
    asset = CatalogAsset(AssetId("retention-asset"), "file", "input.csv")
    catalog.create_asset(workspace_id, asset, now=NOW)
    revisions = (
        AssetRevision(AssetRef(asset.id, AssetVersion("v1")), content_digest="a" * 64),
        AssetRevision(AssetRef(asset.id, AssetVersion("v2")), content_digest="b" * 64),
    )
    for revision in revisions:
        catalog.put_revision(workspace_id, revision, now=NOW)

    assert catalog.list_revisions(workspace_id, asset.id) == revisions


def test_sqlite_catalog_filters_lineage_by_execution_with_a_bound(tmp_path: Path) -> None:
    database = tmp_path / "ronin.db"
    workspaces = SqliteWorkspaceStore(database, migration_now=NOW)
    catalog = SqliteCatalogStore(database, migration_now=NOW)
    workspace_id = WorkspaceId("lineage-execution-ws")
    workspaces.create_workspace(Workspace(workspace_id, "Lineage execution"), now=NOW)
    source = AssetRef(AssetId("source"), AssetVersion("v1"))
    target_one = AssetRef(AssetId("target-one"), AssetVersion("v1"))
    target_two = AssetRef(AssetId("target-two"), AssetVersion("v1"))
    for ref in (source, target_one, target_two):
        catalog.create_asset(
            workspace_id,
            CatalogAsset(ref.asset_id, "table", str(ref.asset_id)),
            now=NOW,
        )
        catalog.put_revision(workspace_id, AssetRevision(ref), now=NOW)
    first = LineageEdge(
        source,
        target_one,
        operation="write",
        mode="observed",
        execution_ref="run-one",
    )
    second = LineageEdge(
        source,
        target_two,
        operation="write",
        mode="observed",
        execution_ref="run-two",
    )
    catalog.put_lineage(workspace_id, first, now=NOW)
    catalog.put_lineage(workspace_id, second, now=NOW)

    assert catalog.downstream_for_execution(workspace_id, source, "run-one") == (first,)
    assert catalog.downstream_for_execution(workspace_id, source, "run-two") == (second,)
    with pytest.raises(ValueError, match="limit"):
        catalog.downstream_for_execution(workspace_id, source, "run-one", limit=0)


def test_sqlite_catalog_retention_limits_fail_closed(tmp_path: Path) -> None:
    workspaces = SqliteWorkspaceStore(tmp_path / "ronin.db", migration_now=NOW)
    catalog = SqliteCatalogStore(tmp_path / "ronin.db", migration_now=NOW)
    workspace_id = WorkspaceId("retention-bounds-ws")
    workspaces.create_workspace(Workspace(workspace_id, "Retention bounds"), now=NOW)
    first = CatalogAsset(AssetId("asset-a"), "file", "a.csv")
    second = CatalogAsset(AssetId("asset-b"), "file", "b.csv")
    for asset in (first, second):
        catalog.create_asset(workspace_id, asset, now=NOW)
    assert catalog.list_assets(workspace_id, limit=2) == (first, second)
    with pytest.raises(ValueError, match="catalog asset inventory exceeded"):
        catalog.list_assets(workspace_id, limit=1)
    workspaces.create_workspace(Workspace(WorkspaceId("retention-bounds-ws-2"), "Extra"), now=NOW)
    with pytest.raises(ValueError, match="workspace inventory exceeded"):
        workspaces.list_workspaces(limit=1)
