from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest
import studio_sql.duckdb_engine as duckdb_engine_module
from studio_core import AssetId, Workspace, WorkspaceId
from studio_execution.lakehouse import write_governed_parquet
from studio_lakehouse import inspect_parquet, read_parquet_rows, write_parquet_rows
from studio_sql import (
    DuckDbSqlEngine,
    ProjectScopedDuckDbSqlEngine,
    SqlRelationUnavailableError,
    SqlResultLimitError,
    SqlTimeoutError,
    SqlValidationError,
)
from studio_storage import SqliteCatalogStore, SqliteWorkspaceStore

pytest.importorskip("pyarrow")
duckdb = pytest.importorskip("duckdb")

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


def test_parquet_round_trip_preserves_temporal_decimal_nested_and_null_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / "typed.parquet"
    rows = (
        {
            "day": date(2026, 9, 22),
            "instant": datetime(2026, 9, 22, 12, 30, tzinfo=UTC),
            "amount": Decimal("12.34"),
            "tags": ["a", "b"],
            "metadata": {"source": "test"},
            "optional": None,
        },
    )
    write_parquet_rows(path, rows)
    restored = read_parquet_rows(path)
    assert restored == rows


def test_parquet_write_atomically_replaces_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "data" / "events.parquet"
    write_parquet_rows(path, ({"id": 1},))
    first_digest = inspect_parquet(path).sha256
    write_parquet_rows(path, ({"id": 2},))
    second = inspect_parquet(path)
    assert second.sha256 != first_digest
    assert read_parquet_rows(path) == ({"id": 2},)
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_parquet_reads_enforce_bounds_and_projection_shape(tmp_path: Path) -> None:
    path = tmp_path / "events.parquet"
    write_parquet_rows(path, ({"id": 1},))
    with pytest.raises(ValueError, match="between 0 and 100000"):
        read_parquet_rows(path, limit=100_001)
    with pytest.raises(ValueError, match="non-empty"):
        read_parquet_rows(path, columns=("",))
    with pytest.raises(ValueError, match="unique"):
        read_parquet_rows(path, columns=("id", "id"))


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
            'SELECT "group", sum(value) AS total FROM events GROUP BY "group" ORDER BY "group"'
        )

    assert tuple(column.name for column in result.columns) == ("group", "total")
    assert result.rows == (("a", 5), ("b", 7))


def test_duckdb_accepts_normalized_sql_scalar_bindings() -> None:
    with DuckDbSqlEngine() as engine:
        result = engine.execute(
            "SELECT ? AS nullable, ? AS enabled, ? AS count, ? AS ratio, ? AS label",
            (None, True, 12, 1.25, "events"),
        )
    assert tuple(column.name for column in result.columns) == (
        "nullable",
        "enabled",
        "count",
        "ratio",
        "label",
    )
    assert result.rows == ((None, True, 12, 1.25, "events"),)


def test_duckdb_engine_interrupts_a_query_at_its_execution_deadline(monkeypatch) -> None:
    entered = Event()
    interrupted = Event()

    class Cursor:
        description = (("value", "INTEGER"),)

        def fetchall(self):
            return []

        def fetchmany(self, _limit):
            return [(1,)]

    class Connection:
        def execute(self, sql, _parameters=()):
            if "information_schema.tables" in sql:
                return Cursor()
            if sql.startswith("SELECT"):
                entered.set()
                if not interrupted.wait(timeout=1):
                    raise AssertionError("execution deadline did not interrupt the query")
                raise RuntimeError("interrupted")
            return Cursor()

        def interrupt(self):
            interrupted.set()

        def close(self):
            return None

    connection = Connection()
    monkeypatch.setattr(
        duckdb_engine_module,
        "_duckdb",
        lambda: SimpleNamespace(connect=lambda **_kwargs: connection),
    )
    engine = DuckDbSqlEngine()
    try:
        with pytest.raises(SqlTimeoutError, match="execution time limit"):
            engine.execute("SELECT 1", timeout_ms=25)
        assert entered.is_set()
        assert interrupted.is_set()
    finally:
        engine.close()


def test_duckdb_engine_stops_fetching_when_serialized_result_exceeds_budget() -> None:
    with DuckDbSqlEngine() as engine, pytest.raises(SqlResultLimitError, match="max_result_bytes"):
        engine.execute("SELECT REPEAT('x', 512)", max_result_bytes=128)


def test_sql_reference_engine_bounds_materialized_results(tmp_path: Path) -> None:
    path = tmp_path / "events.parquet"
    write_parquet_rows(path, ({"id": 1}, {"id": 2}))

    with DuckDbSqlEngine() as engine:
        engine.register_parquet("events", str(path))
        with pytest.raises(ValueError, match="max_rows"):
            engine.execute("SELECT * FROM events ORDER BY id", max_rows=1)


def test_sql_reference_engine_bounds_query_text() -> None:
    with DuckDbSqlEngine() as engine, pytest.raises(ValueError, match="SQL text exceeds"):
        engine.execute("SELECT 1 -- " + "x" * (1024 * 1024))


def test_sql_reference_engine_rejects_mutating_or_multiple_statements() -> None:
    with DuckDbSqlEngine() as engine:
        with pytest.raises(ValueError, match="read-only SELECT"):
            engine.execute("CREATE TABLE unsafe (value INTEGER)")
        with pytest.raises(ValueError, match="read-only SELECT"):
            engine.execute("SELECT 1; SELECT 2")
        for query in (
            "WITH rows AS (SELECT 1) SELECT * FROM rows",
            "VALUES (1)",
            "EXPLAIN SELECT 1",
        ):
            with pytest.raises(ValueError, match="read-only SELECT"):
                engine.execute(query)
        for query in (
            "SELECT * FROM read_parquet('outside.parquet')",
            "SELECT * FROM read_csv('outside.csv')",
            "SELECT * FROM 'https://example.invalid/data.parquet'",
            "SELECT * FROM pragma_database_list()",
        ):
            with pytest.raises(ValueError, match="external filesystem"):
                engine.execute(query)


def test_sql_reference_engine_rejects_direct_and_nested_file_relations(
    tmp_path: Path,
) -> None:
    path = tmp_path / "private.parquet"
    write_parquet_rows(path, ({"secret": "not a relation"},))

    with DuckDbSqlEngine() as engine:
        engine.register_parquet("approved_events", str(path))
        assert engine.execute("SELECT secret FROM approved_events").rows == (("not a relation",),)
        for query in (
            f"SELECT * FROM '{path}'",  # noqa: S608 - deliberately untrusted SQL input.
            f"SELECT * FROM '{tmp_path / '*.parquet'}'",  # noqa: S608 - path source regression.
            f"SELECT * FROM (SELECT * FROM '{path}') AS nested",  # noqa: S608 - nested source regression.
            f"SELECT * FROM approved_events, '{path}'",  # noqa: S608 - comma-source regression.
            f"SELECT * FROM approved_events JOIN read_parquet('{path}') AS nested ON true",  # noqa: S608 - table-function regression.
            f"SELECT * FROM approved_events JOIN approved_events AS second ON true, '{path}'",  # noqa: S608 - comma source after JOIN.
            f"SELECT * FROM approved_events UNION SELECT * FROM '{path}'",  # noqa: S608 - compound query regression.
            "SELECT * FROM read_csv_auto('private.csv')",
        ):
            with pytest.raises(SqlValidationError):
                engine.execute(query)


def test_sql_reference_engine_ignores_relation_keywords_in_literals_and_comments() -> None:
    with DuckDbSqlEngine() as engine:
        result = engine.execute("SELECT 'FROM private.parquet' AS note -- JOIN secret")
        dollar_quoted = engine.execute("SELECT $$FROM private.parquet$$ AS note")
    assert result.rows == (("FROM private.parquet",),)
    assert dollar_quoted.rows == (("FROM private.parquet",),)


def test_project_scoped_sql_engines_isolate_relation_collisions(tmp_path: Path) -> None:
    first = tmp_path / "first.parquet"
    second = tmp_path / "second.parquet"
    write_parquet_rows(first, ({"value": 1},))
    write_parquet_rows(second, ({"value": 2},))

    with ProjectScopedDuckDbSqlEngine() as engine:
        engine.register_parquet("project-a", "events", str(first))
        engine.register_parquet("project-b", "events", str(second))
        assert engine.execute("project-a", "SELECT value FROM events").rows == ((1,),)
        assert engine.execute("project-b", "SELECT value FROM events").rows == ((2,),)
        with pytest.raises(SqlRelationUnavailableError):
            engine.execute("project-c", "SELECT value FROM events")


def test_project_scoped_sql_engine_reuses_and_closes_each_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[DuckDbSqlEngine] = []
    closed: list[DuckDbSqlEngine] = []
    original_engine = duckdb_engine_module.DuckDbSqlEngine

    class RecordingEngine(original_engine):
        def __init__(self) -> None:
            super().__init__()
            created.append(self)

        def close(self) -> None:
            closed.append(self)
            super().close()

    monkeypatch.setattr(duckdb_engine_module, "DuckDbSqlEngine", RecordingEngine)
    with ProjectScopedDuckDbSqlEngine() as engine:
        assert engine.execute("project-a", "SELECT 1").rows == ((1,),)
        assert engine.execute("project-a", "SELECT 2").rows == ((2,),)
        assert engine.execute("project-b", "SELECT 3").rows == ((3,),)
        assert len(created) == 2
        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(
                executor.map(
                    lambda value: engine.execute("project-a", "SELECT ?", (value,)).rows[0][0],
                    range(24),
                )
            )
        assert results == list(range(24))
        assert len(created) == 2
    assert len(closed) == 2
    assert {id(item) for item in closed} == {id(item) for item in created}


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
