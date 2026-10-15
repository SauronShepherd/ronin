from __future__ import annotations

import inspect

import pytest
from studio_core import KnowledgeGraph, LocalGraphQueryExecutor, RqlQuery, graph_executor


def test_graph_executor_exposes_the_stable_default_limit() -> None:
    parameter = inspect.signature(LocalGraphQueryExecutor.execute).parameters["max_limit"]
    assert parameter.default == 10_000


def test_graph_executor_rejects_non_ast_queries_with_exact_diagnostic() -> None:
    executor = LocalGraphQueryExecutor(KnowledgeGraph(()))
    with pytest.raises(TypeError, match=".") as error:
        executor.execute("SELECT Customer")  # type: ignore[arg-type]
    assert str(error.value) == "graph executor requires an RqlQuery AST"


@pytest.mark.parametrize("max_limit", [0, 100_001])
def test_graph_executor_rejects_each_limit_boundary_with_exact_diagnostic(max_limit: int) -> None:
    executor = LocalGraphQueryExecutor(KnowledgeGraph(()))
    with pytest.raises(ValueError, match=".") as error:
        executor.execute(RqlQuery("Customer"), max_limit=max_limit)
    assert str(error.value) == "graph max_limit must be between 1 and 100000"


def test_graph_executor_accepts_inclusive_limit_boundaries() -> None:
    executor = LocalGraphQueryExecutor(KnowledgeGraph(()))
    assert executor.execute(RqlQuery("Customer", limit=1), max_limit=1).objects == ()
    assert executor.execute(RqlQuery("Customer", limit=100_000), max_limit=100_000).objects == ()


def test_graph_executor_reports_ast_limit_overflow_exactly() -> None:
    executor = LocalGraphQueryExecutor(KnowledgeGraph(()))
    with pytest.raises(ValueError, match=".") as error:
        executor.execute(RqlQuery("Customer", limit=2), max_limit=1)
    assert str(error.value) == "RQL limit is outside the executor bound"


def test_graph_query_renderer_emits_each_optional_clause_only_when_present() -> None:
    assert graph_executor._render_query(RqlQuery("Customer")) == "SELECT Customer"
    assert graph_executor._render_query(
        RqlQuery(
            "Customer",
            where_field="region",
            where_value="EU",
            traverse_type="Account",
            join_type="Account",
            join_left="customer_id",
            join_right="id",
            limit=3,
        )
    ) == (
        "SELECT Customer WHERE region = 'EU' TRAVERSE Account "
        "JOIN Account ON customer_id = id LIMIT 3"
    )
