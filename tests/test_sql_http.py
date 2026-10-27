from __future__ import annotations

import pytest
from studio_sql import SqlColumn, SqlHTTPAdapter, SqlQueryResult


class Engine:
    def __init__(self) -> None:
        self.request = None

    def execute(
        self,
        project_id,
        sql,
        parameters=(),
        *,
        max_rows=10_000,
        timeout_ms=5_000,
        max_result_bytes=1_048_576,
    ):
        self.request = (project_id, sql, parameters, max_rows, timeout_ms, max_result_bytes)
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
        "max_result_bytes": 1_048_576,
    }
    assert engine.request == ("project-1", "SELECT ?", (1,), 20, 5_000, 1_048_576)


def test_sql_http_adapter_passes_a_valid_execution_timeout() -> None:
    engine = Engine()
    result = SqlHTTPAdapter(engine).query(
        "project-1", {"sql": "SELECT 1", "timeout_ms": 250, "max_result_bytes": 512}
    )
    assert engine.request == ("project-1", "SELECT 1", (), 10_000, 250, 512)
    assert result["max_result_bytes"] == 512


def test_sql_http_adapter_rejects_unimplemented_profile_fields() -> None:
    engine = Engine()
    with pytest.raises(ValueError, match="unknown fields"):
        SqlHTTPAdapter(engine).query("project-1", {"sql": "SELECT 1", "profile": "queryflux"})
    assert engine.request is None


def test_sql_http_adapter_normalizes_explicitly_typed_bindings() -> None:
    engine = Engine()
    SqlHTTPAdapter(engine).query(
        "project-1",
        {
            "sql": "SELECT ?, ?, ?, ?, ?",
            "parameters": [
                {"type": "null", "value": None},
                {"type": "boolean", "value": True},
                {"type": "integer", "value": 12},
                {"type": "float", "value": 12},
                {"type": "string", "value": "12"},
            ],
        },
    )
    assert engine.request[2] == (None, True, 12, 12.0, "12")


@pytest.mark.parametrize(
    "parameter",
    [
        {"type": "integer", "value": True},
        {"type": "boolean", "value": 1},
        {"type": "float", "value": float("inf")},
        {"type": "binary", "value": "AA=="},
        {"type": "string", "value": "x", "extra": 1},
        {"type": "integer", "value": 2**63},
    ],
)
def test_sql_http_adapter_rejects_ambiguous_or_unsupported_typed_bindings(
    parameter: object,
) -> None:
    engine = Engine()
    with pytest.raises(ValueError, match="SQL parameter"):
        SqlHTTPAdapter(engine).query("project-1", {"sql": "SELECT ?", "parameters": [parameter]})
    assert engine.request is None


def test_sql_http_adapter_enforces_parameter_count_and_text_limits() -> None:
    engine = Engine()
    with pytest.raises(ValueError, match="count limit"):
        SqlHTTPAdapter(engine).query("project-1", {"sql": "SELECT 1", "parameters": [None] * 1001})
    with pytest.raises(ValueError, match="text limit"):
        SqlHTTPAdapter(engine).query(
            "project-1",
            {"sql": "SELECT ?", "parameters": [{"type": "string", "value": "x" * 524_289}]},
        )
    assert engine.request is None


def test_sql_http_adapter_accepts_exact_parameter_count_and_text_limits() -> None:
    engine = Engine()
    SqlHTTPAdapter(engine).query("project-1", {"sql": "SELECT 1", "parameters": [None] * 1000})
    assert len(engine.request[2]) == 1000

    maximum_text = "x" * 524_288
    SqlHTTPAdapter(engine).query(
        "project-1", {"sql": "SELECT ?", "parameters": [{"type": "string", "value": maximum_text}]}
    )
    assert engine.request[2] == (maximum_text,)


def test_sql_http_adapter_rejects_results_over_the_serialized_byte_budget() -> None:
    class LargeResultEngine(Engine):
        def execute(
            self,
            _project_id,
            _sql,
            _parameters=(),
            *,
            max_rows=10_000,
            timeout_ms=5_000,
            max_result_bytes=1_048_576,
        ):
            self.request = (
                _project_id,
                _sql,
                _parameters,
                max_rows,
                timeout_ms,
                max_result_bytes,
            )
            return SqlQueryResult((SqlColumn("value", "VARCHAR"),), (("x" * 512,),))

    with pytest.raises(ValueError, match="max_result_bytes"):
        SqlHTTPAdapter(LargeResultEngine()).query(
            "project-1", {"sql": "SELECT 1", "max_result_bytes": 128}
        )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"sql": "SELECT 1", "parameters": "bad"},
        {"sql": "SELECT 1", "max_rows": 0},
        {"sql": "SELECT 1", "timeout_ms": True},
        {"sql": "SELECT 1", "timeout_ms": 60_001},
        {"sql": "SELECT 1", "max_result_bytes": False},
        {"sql": "SELECT 1", "max_result_bytes": 10_485_761},
    ],
)
def test_sql_http_adapter_rejects_invalid_requests(body: object) -> None:
    with pytest.raises(
        ValueError, match="(sql|parameters|max_rows|body|timeout_ms|max_result_bytes)"
    ):
        SqlHTTPAdapter(Engine()).query("project-1", body)


@pytest.mark.parametrize("sql", ["INSERT INTO t VALUES (1)", "UPDATE t SET x=1", "DROP TABLE t"])
def test_sql_http_adapter_rejects_mutating_statements(sql: str) -> None:
    with pytest.raises(ValueError, match="read-only"):
        SqlHTTPAdapter(Engine()).query("project-1", {"sql": sql})


@pytest.mark.parametrize(
    "sql", ["WITH rows AS (SELECT 1) SELECT * FROM rows", "VALUES (1)", "EXPLAIN SELECT 1"]
)
def test_sql_http_adapter_rejects_statement_forms_outside_shared_engine_contract(
    sql: str,
) -> None:
    engine = Engine()
    with pytest.raises(ValueError, match="read-only SELECT"):
        SqlHTTPAdapter(engine).query("project-1", {"sql": sql})
    assert engine.request is None


@pytest.mark.parametrize("sql", [" SELECT 1", "SELECT 1 ", "SELECT 1; SELECT 2"])
def test_sql_http_adapter_rejects_untrimmed_or_multi_statement_sql(sql: str) -> None:
    engine = Engine()
    with pytest.raises(ValueError, match="(trimmed|read-only SELECT)"):
        SqlHTTPAdapter(engine).query("project-1", {"sql": sql})
    assert engine.request is None
