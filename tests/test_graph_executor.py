from __future__ import annotations

import pytest
from studio_core import (
    KnowledgeGraph,
    KnowledgeObject,
    KnowledgeObjectRef,
    LocalGraphQueryExecutor,
    RqlQuery,
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


def test_local_graph_executor_rejects_zero_query_limit() -> None:
    executor = LocalGraphQueryExecutor(KnowledgeGraph(()))
    with pytest.raises(ValueError, match="configured bound"):
        executor.execute(RqlQuery("Customer", limit=0))


def test_local_graph_executor_renders_where_traverse_join_and_limit_together() -> None:
    customer = KnowledgeObjectRef("Customer", (("id", "1"),))
    account = KnowledgeObjectRef("Account", (("id", "a"),))
    graph = KnowledgeGraph(
        (
            KnowledgeObject(customer, (("region", "EU"), ("account_id", "a"))),
            KnowledgeObject(account, (("customer_id", "1"),)),
        ),
        links=((customer, account),),
    )
    query = RqlQuery(
        "Customer",
        where_field="region",
        where_value="EU",
        traverse_type="Account",
        join_type="Account",
        join_left="customer_id",
        join_right="customer_id",
        limit=1,
    )

    result = LocalGraphQueryExecutor(graph).execute(query, max_limit=2)

    assert tuple(item.ref for item in result.objects) == (account,)


def test_local_graph_executor_uses_executor_bound_when_ast_has_no_limit() -> None:
    objects = tuple(
        KnowledgeObject(KnowledgeObjectRef("Customer", (("id", str(i)),)), ()) for i in range(3)
    )

    result = LocalGraphQueryExecutor(KnowledgeGraph(objects)).execute(
        RqlQuery("Customer"), max_limit=2
    )

    assert len(result.objects) == 2


def test_local_graph_executor_rejects_ast_limit_above_executor_bound() -> None:
    with pytest.raises(ValueError, match="outside the executor bound"):
        LocalGraphQueryExecutor(KnowledgeGraph(())).execute(
            RqlQuery("Customer", limit=3), max_limit=2
        )
