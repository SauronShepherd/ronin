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
    GraphQueryIR,
    GraphQueryResult,
    GraphResourceBudgetExceeded,
    GraphSnapshot,
    GraphTraverse,
    NativeGraphProvider,
    RqlSyntaxError,
    SqliteGraphReadSession,
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
        parse_rql("x" * 65_537)
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
    assert store.neighbors(
        snapshot.ontology_id,
        snapshot.ontology_version,
        snapshot.objects[1].ref,
        link_type="owns",
        direction="in",
    ) == (snapshot.objects[0],)

    replacement = GraphSnapshot(
        snapshot.ontology_id, snapshot.ontology_version, (snapshot.objects[0],)
    )
    store.replace_snapshot(replacement)
    assert store.scan_objects(snapshot.ontology_id, snapshot.ontology_version, "Order") == ()


def test_sqlite_read_snapshot_does_not_mix_concurrent_replacement(tmp_path: Path) -> None:
    store = SqliteGraphStore(tmp_path / "graph.sqlite")
    original = _snapshot()
    customer = original.objects[0]
    original_order = original.objects[1]
    replacement_order = GraphObject(
        KnowledgeObjectRef("Order", (("id", "replacement"),)),
        (("name", "replacement"),),
    )
    replacement = GraphSnapshot(
        original.ontology_id,
        original.ontology_version,
        (customer, replacement_order),
        (GraphLink("owns", customer.ref, replacement_order.ref),),
    )
    store.replace_snapshot(original)

    with store.read_snapshot() as reader:
        assert reader.scan_objects(original.ontology_id, original.ontology_version, "Customer") == (
            customer,
        )
        store.replace_snapshot(replacement)
        assert (
            reader.get_object(original.ontology_id, original.ontology_version, original_order.ref)
            == original_order
        )
        assert reader.neighbors(
            original.ontology_id,
            original.ontology_version,
            customer.ref,
            link_type="owns",
            direction="out",
        ) == (original_order,)

    assert store.neighbors(
        original.ontology_id,
        original.ontology_version,
        customer.ref,
        link_type="owns",
        direction="out",
    ) == (replacement_order,)


def test_native_graph_query_pins_snapshot_while_replacement_commits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SqliteGraphStore(tmp_path / "graph.sqlite")
    original = _snapshot()
    customer, original_order = original.objects
    replacement_order = GraphObject(
        KnowledgeObjectRef("Order", (("id", "replacement"),)),
        (("name", "replacement"),),
    )
    replacement = GraphSnapshot(
        original.ontology_id,
        original.ontology_version,
        (customer, replacement_order),
        (GraphLink("owns", customer.ref, replacement_order.ref),),
    )
    store.replace_snapshot(original)
    scan_objects = SqliteGraphReadSession.scan_objects

    def replace_after_root_scan(
        reader: SqliteGraphReadSession,
        ontology_id: OntologyId,
        ontology_version: str,
        object_type: str,
        *,
        limit: int | None = None,
    ) -> tuple[GraphObject, ...]:
        objects = scan_objects(reader, ontology_id, ontology_version, object_type, limit=limit)
        if object_type == "Customer":
            store.replace_snapshot(replacement)
        return objects

    monkeypatch.setattr(SqliteGraphReadSession, "scan_objects", replace_after_root_scan)
    result = NativeGraphProvider(store, original.ontology_id, original.ontology_version).execute(
        GraphQueryIR(
            "Customer",
            traverse=GraphTraverse("owns", "out", 1),
            return_fields=("name",),
        )
    )

    assert result == GraphQueryResult(((("name", "A-9"),),))
    assert (
        store.get_object(original.ontology_id, original.ontology_version, original_order.ref)
        is None
    )


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


def _fanout_snapshot(fanout: int) -> GraphSnapshot:
    customer = GraphObject(
        KnowledgeObjectRef("Customer", (("id", "customer"),)),
        (("name", "customer"),),
    )
    orders = tuple(
        GraphObject(
            KnowledgeObjectRef("Order", (("id", str(index)),)),
            (("name", f"order-{index}"),),
        )
        for index in range(fanout)
    )
    links = tuple(GraphLink("owns", customer.ref, order.ref) for order in orders)
    return GraphSnapshot(OntologyId("sales"), "v1", (customer, *orders), links)


def test_native_provider_hard_stops_when_node_scan_exceeds_budget(tmp_path: Path) -> None:
    store = SqliteGraphStore(tmp_path / "graph.sqlite")
    snapshot = GraphSnapshot(
        OntologyId("sales"),
        "v1",
        tuple(
            GraphObject(
                KnowledgeObjectRef("Customer", (("id", str(index)),)),
                (("name", f"customer-{index}"),),
            )
            for index in range(3)
        ),
    )
    store.replace_snapshot(snapshot)
    provider = NativeGraphProvider(store, snapshot.ontology_id, snapshot.ontology_version)
    query = GraphQueryIR(
        "Customer",
        return_fields=("_key",),
        limit=1,
        max_examined_nodes=2,
    )

    with pytest.raises(GraphResourceBudgetExceeded, match="node budget of 2"):
        provider.execute(query)


def test_native_provider_counts_edges_even_when_result_limit_is_one(tmp_path: Path) -> None:
    store = SqliteGraphStore(tmp_path / "graph.sqlite")
    snapshot = _fanout_snapshot(3)
    store.replace_snapshot(snapshot)
    provider = NativeGraphProvider(store, snapshot.ontology_id, snapshot.ontology_version)
    query = GraphQueryIR(
        "Customer",
        traverse=GraphTraverse("owns", "out", 1),
        return_fields=("_key",),
        limit=1,
        max_examined_nodes=10,
        max_examined_edges=2,
    )

    with pytest.raises(GraphResourceBudgetExceeded, match="edge budget of 2"):
        provider.execute(query)


def test_native_provider_enforces_node_budget_during_traversal(tmp_path: Path) -> None:
    store = SqliteGraphStore(tmp_path / "graph.sqlite")
    snapshot = _fanout_snapshot(3)
    store.replace_snapshot(snapshot)
    provider = NativeGraphProvider(store, snapshot.ontology_id, snapshot.ontology_version)
    query = GraphQueryIR(
        "Customer",
        traverse=GraphTraverse("owns", "out", 1),
        return_fields=("_key",),
        max_examined_nodes=3,
        max_examined_edges=10,
    )

    with pytest.raises(GraphResourceBudgetExceeded, match="node budget of 3"):
        provider.execute(query)


def test_native_provider_batches_neighbors_and_applies_result_limit(tmp_path: Path) -> None:
    store = SqliteGraphStore(tmp_path / "graph.sqlite")
    snapshot = _fanout_snapshot(5)
    store.replace_snapshot(snapshot)
    statements: list[str] = []
    connections = []
    connect = store._connect

    def tracked_connect():
        connection = connect()
        connections.append(connection)
        connection.set_trace_callback(statements.append)
        return connection

    store._connect = tracked_connect  # type: ignore[method-assign]
    provider = NativeGraphProvider(store, snapshot.ontology_id, snapshot.ontology_version)
    result = provider.execute(
        GraphQueryIR(
            "Customer",
            traverse=GraphTraverse("owns", "out", 1),
            return_fields=("_key",),
            limit=1,
            max_examined_nodes=10,
            max_examined_edges=10,
        )
    )

    selects = [
        statement for statement in statements if statement.lstrip().upper().startswith("SELECT")
    ]
    assert len(selects) == 2
    assert len(connections) == 1
    assert result == GraphQueryResult(((("_key", "id=0"),),))


def test_graph_store_chunks_large_frontiers_and_honors_global_neighbor_limit(
    tmp_path: Path,
) -> None:
    sources = tuple(
        GraphObject(KnowledgeObjectRef("Customer", (("id", f"{index:04d}"),)), ())
        for index in range(501)
    )
    targets = tuple(
        GraphObject(KnowledgeObjectRef("Order", (("id", f"{index:04d}"),)), ())
        for index in range(501)
    )
    snapshot = GraphSnapshot(
        OntologyId("sales"),
        "v1",
        (*sources, *targets),
        tuple(
            GraphLink("owns", source.ref, target.ref)
            for source, target in zip(sources, targets, strict=True)
        ),
    )
    store = SqliteGraphStore(tmp_path / "graph.sqlite")
    store.replace_snapshot(snapshot)

    neighbors = store.neighbors_many(
        snapshot.ontology_id,
        snapshot.ontology_version,
        tuple(source.ref for source in sources),
        link_type="owns",
        direction="out",
        limit=501,
    )
    limited_neighbors = store.neighbors_many(
        snapshot.ontology_id,
        snapshot.ontology_version,
        tuple(source.ref for source in sources),
        link_type="owns",
        direction="out",
        limit=3,
    )

    assert tuple(item.ref for item in neighbors) == tuple(item.ref for item in targets)
    assert tuple(item.ref for item in limited_neighbors) == tuple(item.ref for item in targets[:3])


def test_graph_store_rejects_invalid_bounded_read_arguments(tmp_path: Path) -> None:
    store = SqliteGraphStore(tmp_path / "graph.sqlite")
    ontology_id = OntologyId("sales")
    ref = KnowledgeObjectRef("Customer", (("id", "1"),))

    with pytest.raises(ValueError, match="scan limit must be an integer"):
        store.scan_objects(ontology_id, "v1", "Customer", limit=True)
    with pytest.raises(ValueError, match="neighbor limit must be an integer"):
        store.neighbors_many(
            ontology_id,
            "v1",
            (ref,),
            link_type="owns",
            direction="out",
            limit=1.5,
        )
    with pytest.raises(ValueError, match="direction must be out or in"):
        store.neighbors_many(
            ontology_id,
            "v1",
            (ref,),
            link_type="owns",
            direction="sideways",
            limit=1,
        )  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"limit": True}, "graph query limit must be an integer"),
        ({"limit": 1.5}, "graph query limit must be an integer"),
        ({"max_examined_nodes": False}, "graph max_examined_nodes must be an integer"),
        ({"max_examined_edges": 2.5}, "graph max_examined_edges must be an integer"),
        (
            {"max_examined_edges": 1_000_001},
            "graph max_examined_edges must be between 1 and 1000000",
        ),
    ],
)
def test_graph_query_rejects_non_integer_execution_budgets(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        GraphQueryIR("Customer", **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("depth", [True, 1.5])
def test_graph_traverse_rejects_non_integer_depth(depth: int | float) -> None:
    with pytest.raises(ValueError, match="graph traverse depth must be an integer"):
        GraphTraverse("owns", depth=depth)  # type: ignore[arg-type]
