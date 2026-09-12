from __future__ import annotations

from pathlib import Path

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
