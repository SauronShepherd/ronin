import pytest
from studio_semantic import (
    SemanticDimension,
    SemanticJoin,
    SemanticModel,
    compile_join_chain,
    compile_join_query,
    compile_join_sql,
)


def test_semantic_join_compiles_deterministic_quoted_sql() -> None:
    left = SemanticModel("orders", "Orders", "orders")
    right = SemanticModel("customers", "Customers", "customers")
    sql = compile_join_sql(left, right, SemanticJoin("customer_id", "id", "left"))
    assert sql == (
        'FROM "orders" AS "orders" LEFT JOIN "customers" AS "customers" ON '
        '"orders"."customer_id" = "customers"."id"'
    )


def test_semantic_join_rejects_unsafe_identifiers_and_types() -> None:
    with pytest.raises(ValueError, match="identifier"):
        SemanticJoin("customer-id", "id")
    with pytest.raises(ValueError, match="join type"):
        SemanticJoin("customer_id", "id", "cross")


def test_semantic_join_query_projects_declared_columns_only() -> None:
    left = SemanticModel("orders", "Orders", "orders", (SemanticDimension("id", "id"),))
    right = SemanticModel(
        "customers", "Customers", "customers", (SemanticDimension("name", "name"),)
    )
    sql = compile_join_query(left, right, SemanticJoin("customer_id", "id"))
    assert sql == (
        'SELECT "orders"."id" AS "orders_id", "customers"."name" AS "customers_name" '
        'FROM "orders" AS "orders" JOIN "customers" AS "customers" ON '
        '"orders"."customer_id" = "customers"."id"'
    )


def test_semantic_join_rejects_alias_collisions() -> None:
    left = SemanticModel("orders", "Orders", "orders", (SemanticDimension("id", "id"),))
    same = SemanticModel("orders", "Other", "other", (SemanticDimension("id", "id"),))
    with pytest.raises(ValueError, match="distinct"):
        compile_join_query(left, same, SemanticJoin("id", "id"))


def test_semantic_join_chain_is_bounded_and_deterministic() -> None:
    base = SemanticModel("orders", "Orders", "orders", (SemanticDimension("id", "id"),))
    customers = SemanticModel(
        "customers", "Customers", "customers", (SemanticDimension("id", "id"),)
    )
    regions = SemanticModel("regions", "Regions", "regions", (SemanticDimension("id", "id"),))
    sql = compile_join_chain(
        base,
        (
            (customers, SemanticJoin("customer_id", "id")),
            (regions, SemanticJoin("region_id", "id", "left")),
        ),
    )
    assert sql.startswith('SELECT "orders"."id" AS "orders_id"')
    assert 'JOIN "customers" AS "customers"' in sql
    assert 'LEFT JOIN "regions" AS "regions"' in sql
    with pytest.raises(ValueError, match="between 1 and 8"):
        compile_join_chain(base, ())
