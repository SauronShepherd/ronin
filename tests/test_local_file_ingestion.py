from __future__ import annotations

from pathlib import Path

import pytest

from studio_core import AssetId, ConnectionDefinition, ConnectionId, Workspace, WorkspaceId
from studio_orchestrator import Instant
from studio_storage import LocalArtifactStore, SqliteCatalogStore, SqliteWorkspaceStore
from studio_storage.local_files import LocalFileConnector

_NOW = Instant("2026-09-12T00:00:00.000000Z")
_WS = WorkspaceId("ws-1")
_CONNECTION = ConnectionDefinition(
    ConnectionId("local-files"),
    "Local files",
    "ronin.local-file",
)


def _stores(tmp_path: Path) -> tuple[SqliteCatalogStore, LocalArtifactStore]:
    database = tmp_path / "ronin.sqlite3"
    workspaces = SqliteWorkspaceStore(database, migration_now=_NOW)
    workspaces.create_workspace(Workspace(_WS, "Workspace"), now=_NOW)
    return (
        SqliteCatalogStore(database, migration_now=_NOW),
        LocalArtifactStore(tmp_path / "artifacts"),
    )


def test_csv_ingestion_creates_snapshot_and_lineage(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source_root.joinpath("people.csv").write_text(
        "id,name\n1,Ada\n2,Grace\n",
        encoding="utf-8",
    )
    catalog, artifacts = _stores(tmp_path)
    connector = LocalFileConnector(source_root)

    result = connector.ingest(
        workspace_id=_WS,
        connection=_CONNECTION,
        relative_path="people.csv",
        target_asset_id=AssetId("people"),
        target_name="People",
        artifact_store=artifacts,
        catalog_store=catalog,
        now=_NOW,
    )

    assert result.checkpoint.strategy == "snapshot"
    assert [field.name for field in result.discovered.fields] == ["id", "name"]
    assert catalog.get_revision(_WS, result.target) is not None
    assert catalog.upstream(_WS, result.target)[0].source == result.source


def test_same_content_is_idempotent(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source_root.joinpath("records.jsonl").write_text(
        '{"id":1,"name":"Ada"}\n',
        encoding="utf-8",
    )
    catalog, artifacts = _stores(tmp_path)
    connector = LocalFileConnector(source_root)
    kwargs = dict(
        workspace_id=_WS,
        connection=_CONNECTION,
        relative_path="records.jsonl",
        target_asset_id=AssetId("records"),
        target_name="Records",
        artifact_store=artifacts,
        catalog_store=catalog,
        now=_NOW,
    )

    first = connector.ingest(**kwargs)
    second = connector.ingest(**kwargs)

    assert second == first
    assert len(catalog.upstream(_WS, first.target)) == 1


def test_connector_rejects_path_escape(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    tmp_path.joinpath("outside.csv").write_text("id\n1\n", encoding="utf-8")
    connector = LocalFileConnector(source_root)

    with pytest.raises(ValueError, match="escapes connector root"):
        connector.discover(_CONNECTION, "../outside.csv")


def test_connector_rejects_symlink(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    target = source_root / "target.csv"
    target.write_text("id\n1\n", encoding="utf-8")
    alias = source_root / "alias.csv"
    alias.symlink_to(target)
    connector = LocalFileConnector(source_root)

    with pytest.raises(ValueError, match="symlinks"):
        connector.discover(_CONNECTION, "alias.csv")
