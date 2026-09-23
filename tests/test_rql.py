import pytest
from studio_core import (
    KnowledgeGraph,
    KnowledgeObject,
    KnowledgeObjectRef,
    RqlResult,
    execute_rql,
    parse_rql,
)


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


def test_rql_bounded_traversal_returns_unique_target_objects() -> None:
    customer = KnowledgeObjectRef("Customer", (("id", "1"),))
    first = KnowledgeObjectRef("Order", (("id", "10"),))
    second = KnowledgeObjectRef("Order", (("id", "11"),))
    graph = KnowledgeGraph(
        (
            KnowledgeObject(customer, (("region", "EU"),)),
            KnowledgeObject(first, (("total", "10"),)),
            KnowledgeObject(second, (("total", "20"),)),
        ),
        ((customer, first), (customer, second), (customer, first)),
    )

    result = execute_rql("SELECT Customer TRAVERSE Order LIMIT 1", graph)

    assert [item.ref for item in result.objects] == [first]


def test_rql_traversal_does_not_return_unrelated_types() -> None:
    customer = KnowledgeObjectRef("Customer", (("id", "1"),))
    graph = KnowledgeGraph(
        (
            KnowledgeObject(customer, ()),
            KnowledgeObject(KnowledgeObjectRef("Order", (("id", "10"),)), ()),
            KnowledgeObject(KnowledgeObjectRef("Store", (("id", "s"),)), ()),
        ),
        ((customer, KnowledgeObjectRef("Order", (("id", "10"),))),),
    )

    assert execute_rql("SELECT Customer TRAVERSE Store", graph).objects == ()


def test_rql_bounded_multi_hop_traversal_returns_terminal_objects() -> None:
    customer = KnowledgeObjectRef("Customer", (("id", "1"),))
    order = KnowledgeObjectRef("Order", (("id", "10"),))
    item = KnowledgeObjectRef("Item", (("id", "100"),))
    graph = KnowledgeGraph(
        (KnowledgeObject(customer, ()), KnowledgeObject(order, ()), KnowledgeObject(item, ())),
        ((customer, order), (order, item)),
    )

    result = execute_rql("SELECT Customer TRAVERSE Order->Item", graph)

    assert [obj.ref for obj in result.objects] == [item]


def test_rql_bounded_typed_join_matches_property_values() -> None:
    graph = KnowledgeGraph(
        (
            KnowledgeObject(KnowledgeObjectRef("Customer", (("id", "1"),)), (("account", "a"),)),
            KnowledgeObject(KnowledgeObjectRef("Customer", (("id", "2"),)), (("account", "b"),)),
            KnowledgeObject(KnowledgeObjectRef("Order", (("id", "10"),)), (("customer", "a"),)),
            KnowledgeObject(KnowledgeObjectRef("Order", (("id", "11"),)), (("customer", "z"),)),
        )
    )
    result = execute_rql("SELECT Customer JOIN Order ON account = customer LIMIT 1", graph)
    assert [item.ref.key for item in result.objects] == [(("id", "10"),)]


def test_rql_parser_exposes_versioned_canonical_ast() -> None:
    query = parse_rql("SELECT Customer JOIN Order ON account = customer LIMIT 3")
    assert query.to_data()["version"] == 1
    assert query.to_data()["join"] == {
        "type": "Order",
        "left": "account",
        "right": "customer",
    }
    assert (
        query.canonical_json()
        == parse_rql("SELECT Customer JOIN Order ON account = customer LIMIT 3").canonical_json()
    )
    assert query == type(query).from_data(query.to_data())


def test_rql_ast_rejects_unknown_or_future_versions() -> None:
    query = parse_rql("SELECT Customer")
    invalid = query.to_data()
    invalid["version"] = 2
    with pytest.raises(ValueError, match="version"):
        type(query).from_data(invalid)
    invalid = query.to_data()
    invalid["unexpected"] = True
    with pytest.raises(ValueError, match="keys"):
        type(query).from_data(invalid)


def test_rql_rejects_unsupported_or_unbounded_limit() -> None:
    graph = KnowledgeGraph(())
    with pytest.raises(ValueError, match="unsupported"):
        execute_rql("DELETE Customer", graph)
    with pytest.raises(ValueError, match="limit"):
        execute_rql("SELECT Customer LIMIT 10001", graph)
    with pytest.raises(ValueError, match="unsupported"):
        execute_rql("SELECT Customer TRAVERSE", graph)


def test_rql_rejects_non_text_query() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        parse_rql(123)  # type: ignore[arg-type]


def test_rql_ast_rejects_non_identifier_fields() -> None:
    query = parse_rql("SELECT Customer")
    invalid = query.to_data()
    invalid["source_type"] = "Customer Type"
    with pytest.raises(ValueError, match="identifier"):
        type(query).from_data(invalid)
