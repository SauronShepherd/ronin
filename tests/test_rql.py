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
    for value in (None, 123, [], {}):
        with pytest.raises(ValueError, match="non-empty"):
            parse_rql(value)  # type: ignore[arg-type]


def test_rql_rejects_empty_and_overlong_queries() -> None:
    with pytest.raises(ValueError, match="unsupported|non-empty"):
        parse_rql("   ")
    with pytest.raises(ValueError, match="at most 2000"):
        parse_rql("SELECT Customer " + ("x" * 2000))


def test_rql_ast_rejects_non_identifier_fields() -> None:
    query = parse_rql("SELECT Customer")
    invalid = query.to_data()
    invalid["source_type"] = "Customer Type"
    with pytest.raises(ValueError, match="identifier"):
        type(query).from_data(invalid)


def test_rql_ast_mapping_and_text_helpers_reject_wrong_shapes() -> None:
    query = parse_rql("SELECT Customer WHERE region = 'EU'")
    invalid = query.to_data()
    invalid["where"] = {1: "EU"}
    with pytest.raises(TypeError, match="where must be an object"):
        type(query).from_data(invalid)

    invalid = query.to_data()
    invalid["where"] = {"field": "region", "value": 1}
    with pytest.raises(ValueError, match="where.value"):
        type(query).from_data(invalid)

    invalid = query.to_data()
    invalid["source_type"] = 1
    with pytest.raises(ValueError, match="source_type"):
        type(query).from_data(invalid)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("where", [], "where must be an object"),
        ("where", {"field": "x"}, "where keys"),
        ("where", {"field": "x", "value": " "}, "where.value"),
        ("join", [], "join must be an object"),
        ("join", {"type": "Order"}, "join keys"),
        ("traverse_type", "Customer->", "typed path"),
        ("limit", 0, "positive integer"),
        ("limit", True, "positive integer"),
    ],
)
def test_rql_ast_rejects_invalid_nested_contracts(field: str, value: object, message: str) -> None:
    data = parse_rql("SELECT Customer").to_data()
    data[field] = value
    with pytest.raises((TypeError, ValueError), match=message):
        type(parse_rql("SELECT Customer")).from_data(data)


def test_rql_enforces_positive_execution_limits_and_preserves_empty_results() -> None:
    graph = KnowledgeGraph(())
    with pytest.raises(ValueError, match="configured bound"):
        execute_rql("SELECT Customer LIMIT 0", graph)
    with pytest.raises(ValueError, match="configured bound"):
        execute_rql("SELECT Customer", graph, max_limit=0)
    assert execute_rql("SELECT Customer", graph).objects == ()


def test_rql_parser_and_ast_diagnostics_are_exact() -> None:
    cases = (
        (
            lambda: parse_rql(123),
            "RQL query must be non-empty and at most 2000 characters",
        ),
        (
            lambda: parse_rql("DELETE Customer"),
            "unsupported RQL; expected SELECT Type [WHERE field = 'value'] "
            "[TRAVERSE TargetType] [JOIN Type ON field = field] [LIMIT n]",
        ),
        (
            lambda: type(parse_rql("SELECT Customer")).from_data(
                {**parse_rql("SELECT Customer").to_data(), "source_type": "Customer Type"}
            ),
            "RQL AST source_type must be a portable identifier",
        ),
        (
            lambda: type(parse_rql("SELECT Customer")).from_data(
                {**parse_rql("SELECT Customer").to_data(), "limit": 0}
            ),
            "RQL AST limit must be a positive integer or null",
        ),
    )
    for invoke, message in cases:
        with pytest.raises(ValueError, match=".") as error:
            invoke()
        assert str(error.value) == message


def test_rql_execution_honors_default_max_limit_and_join_no_match() -> None:
    customers = tuple(
        KnowledgeObject(
            KnowledgeObjectRef("Customer", (("id", str(index)),)),
            (("account", str(index)),),
        )
        for index in range(3)
    )
    orders = (KnowledgeObject(KnowledgeObjectRef("Order", (("id", "10"),)), (("customer", "99"),)),)
    graph = KnowledgeGraph(customers + orders)
    assert len(execute_rql("SELECT Customer", graph, max_limit=2).objects) == 2
    assert execute_rql("SELECT Customer JOIN Order ON account = customer", graph).objects == ()


def test_rql_execution_applies_where_before_traversal_and_join() -> None:
    customer_eu = KnowledgeObjectRef("Customer", (("id", "1"),))
    customer_us = KnowledgeObjectRef("Customer", (("id", "2"),))
    order_eu = KnowledgeObjectRef("Order", (("id", "10"),))
    order_us = KnowledgeObjectRef("Order", (("id", "11"),))
    graph = KnowledgeGraph(
        (
            KnowledgeObject(customer_eu, (("region", "EU"), ("account", "a"))),
            KnowledgeObject(customer_us, (("region", "US"), ("account", "b"))),
            KnowledgeObject(order_eu, (("account", "a"),)),
            KnowledgeObject(order_us, (("account", "b"),)),
        ),
        ((customer_eu, order_eu), (customer_us, order_us)),
    )
    assert execute_rql("SELECT Customer WHERE region = 'EU' TRAVERSE Order", graph).objects == (
        graph.objects[2],
    )
    assert execute_rql(
        "SELECT Customer WHERE region = 'EU' JOIN Order ON account = account", graph
    ).objects == (graph.objects[2],)


def test_rql_parser_preserves_all_clauses_and_canonical_ast() -> None:
    query = parse_rql(
        "SELECT Customer WHERE region = 'EU' TRAVERSE Order->Item "
        "JOIN Purchase ON account = customer LIMIT 7"
    )

    assert query.source_type == "Customer"
    assert query.where_field == "region"
    assert query.where_value == "EU"
    assert query.traverse_type == "Order->Item"
    assert query.join_type == "Purchase"
    assert query.join_left == "account"
    assert query.join_right == "customer"
    assert query.limit == 7
    assert type(query).from_data(query.to_data()) == query


@pytest.mark.parametrize(
    "value",
    ["", " leading", "trailing ", "bad name", "bad/name", "bad->"],
)
def test_rql_ast_rejects_unportable_identifier_and_text_values(value: str) -> None:
    query = parse_rql("SELECT Customer")
    with pytest.raises((TypeError, ValueError)):
        type(query).from_data({**query.to_data(), "source_type": value})
