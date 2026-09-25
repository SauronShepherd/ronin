from __future__ import annotations

import pytest

from studio_core import (
    KnowledgeGraph,
    KnowledgeObject,
    KnowledgeObjectRef,
    LocalGraphQueryExecutor,
    parse_rql,
)


def test_local_graph_executor_runs_frozen_ast() -> None:
    customer = KnowledgeObjectRef("Customer", (("id", "1"),))
    graph = KnowledgeGraph((KnowledgeObject(customer, (("region", "EU"),)),))
    executor = LocalGraphQueryExecutor(graph)
    result = executor.execute(parse_rql("SELECT Customer WHERE region = 'EU' LIMIT 1"))
    assert result.objects[0].ref == customer
    assert "bounded" in executor.capabilities


def test_local_graph_executor_enforces_provider_neutral_limits() -> None:
    executor = LocalGraphQueryExecutor(KnowledgeGraph(()))
    with pytest.raises(ValueError, match="executor bound"):
        executor.execute(parse_rql("SELECT Customer LIMIT 3"), max_limit=2)
