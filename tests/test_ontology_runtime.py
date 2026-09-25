from __future__ import annotations

import pytest

from studio_core import (
    AssetId,
    AssetRef,
    AssetVersion,
    KnowledgeGraph,
    KnowledgeObjectRef,
    LinkType,
    ObjectType,
    OntologyId,
    PropertyDefinition,
    materialize_object_type,
    resolve_link_type,
)


def _object_type() -> ObjectType:
    return ObjectType(
        "Customer",
        AssetRef(AssetId("customers"), AssetVersion("1")),
        ("customer_id",),
        (
            PropertyDefinition("customer_id", "string", "customer_id", True),
            PropertyDefinition("name", "string", "name"),
        ),
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


@pytest.mark.parametrize(
    "value", ["", " leading", "trailing ", "line\nfeed", "line\rfeed", "nul\x00value"]
)
def test_ontology_identifiers_reject_non_canonical_text(value: str) -> None:
    with pytest.raises(ValueError, match="single-line"):
        OntologyId(value)


def test_link_type_rejects_unsupported_cardinality_and_unaligned_fields() -> None:
    with pytest.raises(ValueError, match="unsupported link cardinality"):
        LinkType("link", "Customer", "Order", "invalid", ("id",), ("id",))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-empty and aligned"):
        LinkType("link", "Customer", "Order", "one-to-one", ("id",), ())


def test_object_type_rejects_duplicate_keys_and_unrepresented_key_fields() -> None:
    asset = AssetRef(AssetId("customers"), AssetVersion("1"))
    with pytest.raises(ValueError, match="unique key_fields"):
        ObjectType(
            "Customer",
            asset,
            ("customer_id", "customer_id"),
            (PropertyDefinition("customer_id", "string", "customer_id"),),
        )
    with pytest.raises(ValueError, match="represented by properties"):
        ObjectType(
            "Customer",
            asset,
            ("customer_id",),
            (PropertyDefinition("name", "string", "name"),),
        )


def test_resolve_link_type_joins_references_and_enforces_cardinality() -> None:
    source = materialize_object_type(_object_type(), ({"customer_id": 7, "name": "Ada"},))
    target_type = ObjectType(
        "Order",
        AssetRef(AssetId("orders"), AssetVersion("1")),
        ("customer_id",),
        (
            PropertyDefinition("customer_id", "string", "customer_id", True),
            PropertyDefinition("order_id", "string", "order_id", True),
        ),
    )
    targets = materialize_object_type(target_type, ({"customer_id": 7, "order_id": "o1"},))
    link = LinkType(
        "customer_orders", "Customer", "Order", "one-to-many", ("customer_id",), ("customer_id",)
    )
    assert len(resolve_link_type(link, source, targets)) == 1
    graph = KnowledgeGraph(source + targets, resolve_link_type(link, source, targets))
    assert graph.objects_of_type("Order") == targets
    assert graph.neighbors(source[0].ref) == (targets[0].ref,)


def test_resolve_link_type_rejects_bounds_and_mismatched_object_types() -> None:
    source = materialize_object_type(_object_type(), ({"customer_id": 7, "name": "Ada"},))
    target_type = ObjectType(
        "Order",
        AssetRef(AssetId("orders"), AssetVersion("1")),
        ("order_id",),
        (
            PropertyDefinition("customer_id", "string", "customer_id", True),
            PropertyDefinition("order_id", "string", "order_id", True),
        ),
    )
    targets = materialize_object_type(target_type, ({"customer_id": 7, "order_id": "o1"},))
    link = LinkType(
        "customer_orders", "Customer", "Order", "many-to-many", ("customer_id",), ("customer_id",)
    )
    with pytest.raises(ValueError, match="max_links"):
        resolve_link_type(link, source, targets, max_links=0)
    wrong = materialize_object_type(_object_type(), ({"customer_id": 8, "name": "Grace"},))
    with pytest.raises(ValueError, match="target_type"):
        resolve_link_type(link, source, wrong)


def test_resolve_link_type_enforces_target_cardinality_and_returns_sorted_pairs() -> None:
    source_type = ObjectType(
        "Customer",
        AssetRef(AssetId("customers"), AssetVersion("1")),
        ("source_id",),
        (
            PropertyDefinition("customer_id", "string", "customer_id", True),
            PropertyDefinition("source_id", "string", "source_id", True),
        ),
    )
    target_type = ObjectType(
        "Order",
        AssetRef(AssetId("orders"), AssetVersion("1")),
        ("order_id",),
        (
            PropertyDefinition("customer_id", "string", "customer_id", True),
            PropertyDefinition("order_id", "string", "order_id", True),
        ),
    )
    sources = materialize_object_type(
        source_type, ({"customer_id": 1, "source_id": "s1"}, {"customer_id": 1, "source_id": "s2"})
    )
    targets = materialize_object_type(
        target_type, ({"customer_id": 1, "order_id": "a"}, {"customer_id": 2, "order_id": "b"})
    )
    link = LinkType(
        "orders", "Customer", "Order", "one-to-many", ("customer_id",), ("customer_id",)
    )
    pairs = resolve_link_type(link, sources, targets)
    assert pairs == tuple(sorted(pairs, key=lambda pair: (pair[0], pair[1])))
    duplicate_target = materialize_object_type(target_type, ({"customer_id": 1, "order_id": "c"},))
    with pytest.raises(ValueError, match="source-side cardinality"):
        resolve_link_type(link, sources, targets[:1] + duplicate_target)


def test_resolve_link_type_rejects_source_mismatch_link_limit_and_one_to_one() -> None:
    source = materialize_object_type(_object_type(), ({"customer_id": 7, "name": "Ada"},))
    target_type = ObjectType(
        "Order",
        AssetRef(AssetId("orders"), AssetVersion("1")),
        ("order_id",),
        (
            PropertyDefinition("customer_id", "string", "customer_id", True),
            PropertyDefinition("order_id", "string", "order_id", True),
        ),
    )
    targets = materialize_object_type(
        target_type, ({"customer_id": 7, "order_id": "a"}, {"customer_id": 7, "order_id": "b"})
    )
    many = LinkType(
        "orders", "Customer", "Order", "many-to-many", ("customer_id",), ("customer_id",)
    )
    with pytest.raises(ValueError, match="source objects"):
        resolve_link_type(many, targets, targets)
    with pytest.raises(ValueError, match="exceeds configured limit"):
        resolve_link_type(many, source, targets, max_links=1)
    one_to_one = LinkType(
        "orders", "Customer", "Order", "one-to-one", ("customer_id",), ("customer_id",)
    )
    with pytest.raises(ValueError, match="source-side cardinality"):
        resolve_link_type(one_to_one, source, targets)
