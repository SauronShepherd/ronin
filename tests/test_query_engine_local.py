from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from studio_query_engine import LocalSqlTransport, QueryRequest
from studio_sql import (
    DuckDbSqlEngine,
    SqlColumn,
    SqlQueryResult,
    SqlRelationUnavailableError,
    SqlValidationError,
)


class FakeSqlEngine:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def register_parquet(self, name: str, path: str) -> None:
        del name, path

    def execute(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
        *,
        max_rows: int = 10_000,
    ) -> SqlQueryResult:
        assert parameters == ()
        self.calls.append((sql, max_rows))
        if sql == "SELECT bad":
            raise SqlValidationError("invalid column")
        return SqlQueryResult((SqlColumn("value", "INTEGER"),), ((1,), (2,)))

    def close(self) -> None:
        pass


def test_local_transport_executes_shared_contract() -> None:
    engine = FakeSqlEngine()
    transport = LocalSqlTransport(engine)
    request = QueryRequest("SELECT value", "local", max_rows=7)

    handle, next_uri = transport.submit(request)
    status, page, following = transport.poll(handle, next_uri)

    assert status.state == "succeeded"
    assert page is not None
    assert page.columns == ("value",)
    assert page.rows == ((1,), (2,))
    assert following is None
    assert engine.calls == [("SELECT value", 7)]


def test_local_transport_normalizes_sql_failures_and_cancellation() -> None:
    transport = LocalSqlTransport(FakeSqlEngine())
    handle, next_uri = transport.submit(QueryRequest("SELECT bad", "local"))
    status, page, _ = transport.poll(handle, next_uri)
    assert status.state == "failed"
    assert page is None
    assert "invalid column" in (status.message or "")

    pending, pending_uri = transport.submit(QueryRequest("SELECT value", "local"))
    cancellation = transport.cancel(pending)
    assert cancellation.cancelled is True
    replay = transport.cancel(pending)
    assert replay.cancelled is False
    assert replay.final_state == "cancelled"
    status, page, _ = transport.poll(pending, pending_uri)
    assert status.state == "cancelled"
    assert page is None


def test_local_transport_rejects_unknown_handle() -> None:
    transport = LocalSqlTransport(FakeSqlEngine())
    from studio_query_engine import QueryHandle

    status, page, following = transport.poll(QueryHandle("unknown", "local"), "unknown")
    assert status.state == "failed"
    assert page is None
    assert following is None


def test_local_transport_rejects_handles_from_another_provider() -> None:
    transport = LocalSqlTransport(FakeSqlEngine())
    from studio_query_engine import QueryHandle

    foreign = QueryHandle("query", "other-provider")
    status, page, following = transport.poll(foreign, "query")
    assert status.state == "failed"
    assert "another provider" in (status.message or "")
    assert page is None
    assert following is None
    assert transport.cancel(foreign).final_state == "failed"


def test_duckdb_relation_lifecycle_is_bounded_to_registered_views(tmp_path) -> None:
    parquet = tmp_path / "events.parquet"
    pq.write_table(pa.table({"value": [1, 2]}), parquet)
    with DuckDbSqlEngine() as engine:
        engine.register_parquet("events", str(parquet))
        assert engine.list_relations() == ("events",)
        engine.drop_relation("events")
        assert engine.list_relations() == ()
        with pytest.raises(SqlRelationUnavailableError):
            engine.drop_relation("events")
