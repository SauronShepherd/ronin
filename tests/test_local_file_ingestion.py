from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest
from studio_core import AssetId, ConnectionDefinition, ConnectionId, Workspace, WorkspaceId
from studio_ml.datasets import DatasetResolver
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
    assert DatasetResolver(catalog, artifacts).resolve(_WS, result.target) == [
        {"id": "1", "name": "Ada"},
        {"id": "2", "name": "Grace"},
    ]


def test_ingestion_holds_barrier_through_artifact_and_catalog_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source_root.joinpath("people.csv").write_text("id,name\n1,Ada\n", encoding="utf-8")
    catalog, artifacts = _stores(tmp_path)
    events: list[str] = []

    class Barrier:
        @contextmanager
        def writer(self):
            events.append("lock")
            try:
                yield
            finally:
                events.append("unlock")

        @contextmanager
        def collector(self):
            yield

    original_put_bytes = artifacts.put_bytes
    original_create_asset = catalog.create_asset
    original_put_revision = catalog.put_revision
    original_put_lineage = catalog.put_lineage

    def put_bytes(**kwargs):
        events.append("artifact")
        return original_put_bytes(**kwargs)

    def create_asset(*args, **kwargs):
        events.append("asset")
        return original_create_asset(*args, **kwargs)

    def put_revision(*args, **kwargs):
        events.append("reference")
        return original_put_revision(*args, **kwargs)

    def put_lineage(*args, **kwargs):
        events.append("lineage")
        return original_put_lineage(*args, **kwargs)

    monkeypatch.setattr(artifacts, "put_bytes", put_bytes)
    monkeypatch.setattr(catalog, "create_asset", create_asset)
    monkeypatch.setattr(catalog, "put_revision", put_revision)
    monkeypatch.setattr(catalog, "put_lineage", put_lineage)

    LocalFileConnector(source_root).ingest(
        workspace_id=_WS,
        connection=_CONNECTION,
        relative_path="people.csv",
        target_asset_id=AssetId("people"),
        target_name="People",
        artifact_store=artifacts,
        catalog_store=catalog,
        artifact_reference_barrier=Barrier(),
        now=_NOW,
    )

    assert events == [
        "lock",
        "artifact",
        "asset",
        "asset",
        "reference",
        "reference",
        "lineage",
        "unlock",
    ]


def test_same_content_is_idempotent(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source_root.joinpath("records.jsonl").write_text(
        '{"id":1,"name":"Ada"}\n',
        encoding="utf-8",
    )
    catalog, artifacts = _stores(tmp_path)
    connector = LocalFileConnector(source_root)
    kwargs = {
        "workspace_id": _WS,
        "connection": _CONNECTION,
        "relative_path": "records.jsonl",
        "target_asset_id": AssetId("records"),
        "target_name": "Records",
        "artifact_store": artifacts,
        "catalog_store": catalog,
        "now": _NOW,
    }

    first = connector.ingest(**kwargs)
    second = connector.ingest(**kwargs)

    assert second == first
    assert len(catalog.upstream(_WS, first.target)) == 1
    assert DatasetResolver(catalog, artifacts).resolve(_WS, first.target) == [
        {"id": 1, "name": "Ada"}
    ]


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
    try:
        alias.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable on this host: {exc}")
    connector = LocalFileConnector(source_root)

    with pytest.raises(ValueError, match="symlinks"):
        connector.discover(_CONNECTION, "alias.csv")


@pytest.mark.parametrize(
    ("filename", "contents", "message"),
    [
        ("bad.csv", "id,id\n1,2\n", "unique"),
        ("bad.jsonl", "[]\n", "objects"),
        ("bad.txt", "value\n", "supports only"),
    ],
)
def test_connector_rejects_invalid_input_shapes(
    tmp_path: Path, filename: str, contents: str, message: str
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / filename).write_text(contents, encoding="utf-8")
    connector = LocalFileConnector(source_root)

    with pytest.raises(ValueError, match=message):
        connector.discover(_CONNECTION, filename)


def test_connector_enforces_bounded_reads(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "large.csv").write_text("value\n123\n", encoding="utf-8")
    connector = LocalFileConnector(source_root, max_bytes=3)

    with pytest.raises(ValueError, match="read limit"):
        connector.read("large.csv")
