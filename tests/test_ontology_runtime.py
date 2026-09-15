from __future__ import annotations

import pytest

from studio_core import (
    AssetId,
    AssetRef,
    AssetVersion,
    KnowledgeObjectRef,
    KnowledgeGraph,
    ObjectType,
    PropertyDefinition,
    materialize_object_type,
    LinkType,
    resolve_link_type,
)


def _object_type() -> ObjectType:
    return ObjectType(
        "Customer",
        AssetRef(AssetId("customers"), AssetVersion("1")),
        ("customer_id",),
        (PropertyDefinition("customer_id", "string", "customer_id", True), PropertyDefinition("name", "string", "name")),
    )


def test_materialize_object_type_creates_stable_objects() -> None:
    result = materialize_object_type(_object_type(), ({"customer_id": 7, "name": "Ada"},))
    assert result[0].ref == KnowledgeObjectRef("Customer", (("customer_id", "7"),))
    assert result[0].properties == (("customer_id", 7), ("name", "Ada"))


def test_materialize_rejects_duplicate_or_missing_keys() -> None:
    with pytest.raises(ValueError, match="duplicated"):
        materialize_object_type(_object_type(), ({"customer_id": 7}, {"customer_id": 7}))
    with pytest.raises(ValueError, match="missing required fields"):
        materialize_object_type(_object_type(), ({"name": "Ada"},))


def test_resolve_link_type_joins_references_and_enforces_cardinality() -> None:
    source = materialize_object_type(_object_type(), ({"customer_id": 7, "name": "Ada"},))
    target_type = ObjectType(
        "Order", AssetRef(AssetId("orders"), AssetVersion("1")), ("customer_id",),
        (PropertyDefinition("customer_id", "string", "customer_id", True), PropertyDefinition("order_id", "string", "order_id", True)),
    )
    targets = materialize_object_type(target_type, ({"customer_id": 7, "order_id": "o1"},))
    link = LinkType("customer_orders", "Customer", "Order", "one-to-many", ("customer_id",), ("customer_id",))
    assert len(resolve_link_type(link, source, targets)) == 1
    graph = KnowledgeGraph(source + targets, resolve_link_type(link, source, targets))
    assert graph.objects_of_type("Order") == targets
    assert graph.neighbors(source[0].ref) == (targets[0].ref,)
