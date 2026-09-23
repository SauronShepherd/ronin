from __future__ import annotations

import pytest
from studio_sql import SqlColumn, SqlHTTPAdapter, SqlQueryResult


class Engine:
    def __init__(self) -> None:
        self.request = None

    def execute(self, project_id, sql, parameters=(), *, max_rows=10_000):
        self.request = (project_id, sql, parameters, max_rows)
        return SqlQueryResult((SqlColumn("value", "INTEGER"),), ((1,),))


def test_sql_http_adapter_validates_and_serializes_query() -> None:
    engine = Engine()
    result = SqlHTTPAdapter(engine).query(
        "project-1", {"sql": "SELECT ?", "parameters": [1], "max_rows": 20}
    )
    assert result == {
        "columns": [{"name": "value", "type_name": "INTEGER"}],
        "rows": [[1]],
        "row_count": 1,
        "max_rows": 20,
    }
    assert engine.request == ("project-1", "SELECT ?", (1,), 20)


@pytest.mark.parametrize(
    "body", [{}, {"sql": "SELECT 1", "parameters": "bad"}, {"sql": "SELECT 1", "max_rows": 0}]
)
def test_sql_http_adapter_rejects_invalid_requests(body: object) -> None:
    with pytest.raises(ValueError):
        SqlHTTPAdapter(Engine()).query("project-1", body)


@pytest.mark.parametrize("sql", ["INSERT INTO t VALUES (1)", "UPDATE t SET x=1", "DROP TABLE t"])
def test_sql_http_adapter_rejects_mutating_statements(sql: str) -> None:
    with pytest.raises(ValueError, match="read-only"):
        SqlHTTPAdapter(Engine()).query("project-1", {"sql": sql})
