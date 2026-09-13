from pathlib import Path

import pytest

from studio_core import AssetId, Workspace, WorkspaceId
from studio_execution.lakehouse import write_governed_parquet
from studio_lakehouse import inspect_parquet, read_parquet_rows, write_parquet_rows
from studio_sql import DuckDbSqlEngine
from studio_storage import SqliteCatalogStore, SqliteWorkspaceStore

pytest.importorskip("pyarrow")
pytest.importorskip("duckdb")

_NOW = "2026-09-13T10:30:00.000000Z"
_WS = WorkspaceId("workspace-data-plane")


def test_parquet_round_trip_and_content_metadata(tmp_path: Path) -> None:
    path = tmp_path / "data" / "events.parquet"
    rows = (
        {"id": 1, "group": "a", "value": 2.5},
        {"id": 2, "group": "a", "value": 3.5},
        {"id": 3, "group": "b", "value": 9.0},
    )

    written = write_parquet_rows(path, rows)
    inspected = inspect_parquet(path)
    assert inspected == written
    assert written.rows == 3
    assert written.bytes > 0
    assert len(written.sha256) == 64
    assert read_parquet_rows(path, columns=("id", "group"), limit=2) == (
        {"id": 1, "group": "a"},
        {"id": 2, "group": "a"},
    )


def test_duckdb_reference_engine_queries_registered_parquet(tmp_path: Path) -> None:
    path = tmp_path / "events.parquet"
    write_parquet_rows(
        path,
        (
            {"group": "a", "value": 2},
            {"group": "a", "value": 3},
            {"group": "b", "value": 7},
        ),
    )

    with DuckDbSqlEngine() as engine:
        engine.register_parquet("events", str(path))
        result = engine.execute(
            "SELECT group, sum(value) AS total FROM events GROUP BY group ORDER BY group"
        )

    assert tuple(column.name for column in result.columns) == ("group", "total")
    assert result.rows == (("a", 5), ("b", 7))


def test_sql_reference_engine_bounds_materialized_results(tmp_path: Path) -> None:
    path = tmp_path / "events.parquet"
    write_parquet_rows(path, ({"id": 1}, {"id": 2}))

    with DuckDbSqlEngine() as engine:
        engine.register_parquet("events", str(path))
        with pytest.raises(ValueError, match="max_rows"):
            engine.execute("SELECT * FROM events ORDER BY id", max_rows=1)


def test_governed_parquet_write_commits_content_addressed_catalog_revision(
    tmp_path: Path,
) -> None:
    database = tmp_path / "metadata.db"
    workspaces = SqliteWorkspaceStore(database, migration_now=_NOW)
    workspaces.create_workspace(Workspace(_WS, "Data workspace"), now=_NOW)
    catalog = SqliteCatalogStore(database, migration_now=_NOW)

    result = write_governed_parquet(
        catalog,
        _WS,
        asset_id=AssetId("asset-events-parquet"),
        name="Events Parquet",
        path=tmp_path / "lake" / "events.parquet",
        rows=({"id": 1, "value": 3.0}, {"id": 2, "value": 4.0}),
        project_id="project-data",
        now=_NOW,
    )

    assert result.revision.ref.version.value == result.file.sha256
    assert result.revision.content_digest == result.file.sha256
    assert result.revision.schema_digest is not None
    assert catalog.get_asset(_WS, result.asset.id) == result.asset
    assert catalog.get_revision(_WS, result.revision.ref) == result.revision
