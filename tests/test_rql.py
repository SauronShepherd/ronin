import pytest

from studio_core import KnowledgeGraph, KnowledgeObject, KnowledgeObjectRef, RqlResult, execute_rql


def test_rql_select_where_and_limit() -> None:
    graph = KnowledgeGraph(
        (
            KnowledgeObject(KnowledgeObjectRef("Customer", (("id", "1"),)), (("region", "EU"),)),
            KnowledgeObject(KnowledgeObjectRef("Customer", (("id", "2"),)), (("region", "US"),)),
        )
    )
    result = execute_rql("SELECT Customer WHERE region = 'EU' LIMIT 1", graph)
    assert isinstance(result, RqlResult)
    assert [item.ref.key for item in result.objects] == [(("id", "1"),)]


def test_rql_rejects_unsupported_or_unbounded_limit() -> None:
    graph = KnowledgeGraph(())
    with pytest.raises(ValueError):
        execute_rql("DELETE Customer", graph)
    with pytest.raises(ValueError):
        execute_rql("SELECT Customer LIMIT 10001", graph)
