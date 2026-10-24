from pathlib import Path

import pytest
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_core.ontology import (
    KnowledgeObjectRef,
    LinkType,
    ObjectType,
    OntologyDefinition,
    OntologyId,
    PropertyDefinition,
)
from studio_graph import (
    GraphLink,
    GraphMaterializationError,
    GraphObject,
    GraphQueryResult,
    GraphSnapshot,
    NativeGraphProvider,
    RqlSyntaxError,
    SqliteGraphStore,
    materialize_graph,
    parse_rql,
)


def _snapshot() -> GraphSnapshot:
    customer = GraphObject(
        KnowledgeObjectRef("Customer", (("id", "1"),)),
        (("name", "Ada"), ("score", 7)),
    )
    order = GraphObject(
        KnowledgeObjectRef("Order", (("id", "9"),)),
        (("name", "A-9"),),
    )
    return GraphSnapshot(
        OntologyId("sales"), "v1", (order, customer), (GraphLink("owns", customer.ref, order.ref),)
    )


def test_rql_parser_builds_bounded_query_and_rejects_unsupported_input() -> None:
    query = parse_rql(
        "MATCH Customer WHERE score >= 5 TRAVERSE owns OUT DEPTH 2 RETURN name,_key LIMIT 25"
    )
    assert query.object_type == "Customer"
    assert query.limit == 25
    assert query.return_fields == ("name", "_key")
    assert query.traverse is not None
    assert query.traverse.depth == 2

    for text in (
        "MATCH Customer WHERE score = [] RETURN name",
        "MATCH Customer RETURN name LIMIT 100001",
        "MATCH Customer TRAVERSE owns DEPTH 9 RETURN name",
        "MATCH Customer RETURN name; DROP TABLE graph_objects",
    ):
        with pytest.raises(RqlSyntaxError):
            parse_rql(text)


def test_rql_parser_preserves_quoted_scalar_types_and_rejects_joined_fields() -> None:
    quoted_true = parse_rql('MATCH Customer WHERE name = "true" RETURN name')
    quoted_null = parse_rql('MATCH Customer WHERE name = "null" RETURN name')
    single_quoted = parse_rql("MATCH Customer WHERE name = 'hello world' RETURN name")
    escaped_quote = parse_rql('MATCH Customer WHERE name = "say \\"true\\"" RETURN name')
    bare_true = parse_rql("MATCH Customer WHERE active = true RETURN name")
    separated_fields = parse_rql("MATCH Customer RETURN name , _key")
    unicode_literal = parse_rql('MATCH Customer WHERE name = "café" RETURN name')

    assert quoted_true.filters[0].value == "true"
    assert isinstance(quoted_true.filters[0].value, str)
    assert quoted_null.filters[0].value == "null"
    assert isinstance(quoted_null.filters[0].value, str)
    assert single_quoted.filters[0].value == "hello world"
    assert escaped_quote.filters[0].value == 'say "true"'
    assert unicode_literal.filters[0].value == "café"
    assert bare_true.filters[0].value is True
    assert separated_fields.return_fields == ("name", "_key")
    with pytest.raises(RqlSyntaxError, match="invalid return field"):
        parse_rql("MATCH Customer RETURN name _key")
    with pytest.raises(RqlSyntaxError, match="quoted RQL string is invalid"):
        parse_rql('MATCH Customer WHERE name = "bad\\q" RETURN name')


def test_rql_parser_rejects_oversized_text_and_token_count() -> None:
    with pytest.raises(RqlSyntaxError, match="byte limit"):
        parse_rql("é" * 32_769)
    with pytest.raises(RqlSyntaxError, match="token limit"):
        parse_rql("MATCH Customer RETURN name " + "field " * 4096)
    with pytest.raises(RqlSyntaxError, match="valid Unicode"):
        parse_rql('MATCH Customer WHERE name = "' + "\ud800" + '" RETURN name')


def test_graph_contracts_reject_noncanonical_objects_and_dangling_links() -> None:
    ref = KnowledgeObjectRef("Customer", (("id", "1"),))
    with pytest.raises(ValueError, match="property names must be unique"):
        GraphObject(ref, (("name", "Ada"), ("name", "Grace")))

    unknown = KnowledgeObjectRef("Order", (("id", "9"),))
    with pytest.raises(ValueError, match="must reference known objects"):
        GraphSnapshot(
            OntologyId("sales"), "v1", (GraphObject(ref, ()),), (GraphLink("owns", ref, unknown),)
        )


def test_materialization_uses_governed_keys_and_rejects_missing_required_fields() -> None:
    ontology = OntologyDefinition(
        OntologyId("sales"),
        "v1",
        "Sales",
        (
            ObjectType(
                "Customer",
                AssetRef(AssetId("customers"), AssetVersion("v1")),
                ("id",),
                (
                    PropertyDefinition("id", "string", "id", required=True),
                    PropertyDefinition("name", "string", "customer_name", required=True),
                ),
            ),
        ),
    )
    snapshot = materialize_graph(ontology, {"Customer": [{"id": 1, "customer_name": "Ada"}]})
    assert snapshot.objects[0].ref == KnowledgeObjectRef("Customer", (("id", "1"),))
    assert snapshot.objects[0].property("name") == "Ada"

    with pytest.raises(GraphMaterializationError, match="source field is missing"):
        materialize_graph(ontology, {"Customer": [{"id": 1}]})


def test_materialization_builds_virtual_links_and_checks_cardinality() -> None:
    asset = AssetRef(AssetId("sales"), AssetVersion("v1"))
    customer = ObjectType(
        "Customer",
        asset,
        ("id",),
        (PropertyDefinition("id", "string", "id", required=True),),
    )
    order = ObjectType(
        "Order",
        asset,
        ("id",),
        (
            PropertyDefinition("id", "string", "id", required=True),
            PropertyDefinition("customer_id", "string", "customer_id", required=True),
        ),
    )
    link = LinkType("owns", "Customer", "Order", "one-to-many", ("id",), ("customer_id",))
    ontology = OntologyDefinition(OntologyId("sales"), "v1", "Sales", (customer, order), (link,))
    rows = {
        "Customer": [{"id": "1"}],
        "Order": [{"id": "9", "customer_id": "1"}, {"id": "10", "customer_id": "1"}],
    }

    snapshot = materialize_graph(ontology, rows)
    customer_ref = KnowledgeObjectRef("Customer", (("id", "1"),))
    assert set(snapshot.links) == {
        GraphLink("owns", customer_ref, KnowledgeObjectRef("Order", (("id", "9"),))),
        GraphLink("owns", customer_ref, KnowledgeObjectRef("Order", (("id", "10"),))),
    }

    one_to_one = LinkType("owns", "Customer", "Order", "one-to-one", ("id",), ("customer_id",))
    invalid_ontology = OntologyDefinition(
        OntologyId("sales"), "v1", "Sales", (customer, order), (one_to_one,)
    )
    with pytest.raises(GraphMaterializationError, match="one-to-one cardinality"):
        materialize_graph(invalid_ontology, rows)


def test_sqlite_store_round_trips_snapshot_and_replaces_atomically(tmp_path: Path) -> None:
    store = SqliteGraphStore(tmp_path / "graph.sqlite")
    snapshot = _snapshot()
    assert store.replace_snapshot(snapshot) == snapshot
    assert store.scan_objects(snapshot.ontology_id, snapshot.ontology_version, "Customer") == (
        snapshot.objects[0],
    )
    assert store.get_object(
        snapshot.ontology_id, snapshot.ontology_version, snapshot.objects[0].ref
    )
    assert store.neighbors(
        snapshot.ontology_id,
        snapshot.ontology_version,
        snapshot.objects[0].ref,
        link_type="owns",
        direction="out",
    ) == (snapshot.objects[1],)

    replacement = GraphSnapshot(
        snapshot.ontology_id, snapshot.ontology_version, (snapshot.objects[0],)
    )
    store.replace_snapshot(replacement)
    assert store.scan_objects(snapshot.ontology_id, snapshot.ontology_version, "Order") == ()


def test_native_provider_executes_filters_and_bounded_traversal(tmp_path: Path) -> None:
    store = SqliteGraphStore(tmp_path / "graph.sqlite")
    snapshot = _snapshot()
    store.replace_snapshot(snapshot)
    provider = NativeGraphProvider(store, snapshot.ontology_id, snapshot.ontology_version)

    result = provider.execute(parse_rql("MATCH Customer WHERE score >= 5 RETURN _key,name LIMIT 2"))
    assert result == GraphQueryResult(((("_key", "id=1"), ("name", "Ada")),))

    traversed = provider.execute(
        parse_rql("MATCH Customer WHERE score >= 5 TRAVERSE owns OUT DEPTH 1 RETURN _type,name")
    )
    assert traversed == GraphQueryResult(((("_type", "Order"), ("name", "A-9")),))


def test_native_provider_rejects_missing_return_fields(tmp_path: Path) -> None:
    store = SqliteGraphStore(tmp_path / "graph.sqlite")
    snapshot = _snapshot()
    store.replace_snapshot(snapshot)
    provider = NativeGraphProvider(store, snapshot.ontology_id, snapshot.ontology_version)

    with pytest.raises(KeyError, match="absent from object type"):
        provider.execute(parse_rql("MATCH Customer RETURN missing"))
