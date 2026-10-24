from __future__ import annotations

import pytest
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_core.ontology import (
    LinkCardinality,
    LinkType,
    ObjectType,
    OntologyDefinition,
    OntologyId,
    PropertyDefinition,
    materialize_object_type,
    resolve_link_type,
)
from studio_graph import GraphMaterializationError, materialize_graph

_ASSET = AssetRef(AssetId("records"), AssetVersion("1"))


def _definitions(
    cardinality: LinkCardinality,
) -> tuple[OntologyDefinition, ObjectType, ObjectType, LinkType]:
    source = ObjectType(
        "Source",
        _ASSET,
        ("id",),
        (
            PropertyDefinition("id", "string", "id", required=True),
            PropertyDefinition("join_key", "string", "join_key", required=True),
        ),
    )
    target = ObjectType(
        "Target",
        _ASSET,
        ("id",),
        (
            PropertyDefinition("id", "string", "id", required=True),
            PropertyDefinition("join_key", "string", "join_key", required=True),
        ),
    )
    link = LinkType("related", "Source", "Target", cardinality, ("join_key",), ("join_key",))
    ontology = OntologyDefinition(OntologyId("parity"), "1", "Parity", (source, target), (link,))
    return ontology, source, target, link


@pytest.mark.parametrize(
    ("cardinality", "source_ids", "target_ids", "valid"),
    [
        ("one-to-one", ("s1",), ("t1",), True),
        ("one-to-one", ("s1",), ("t1", "t2"), False),
        ("one-to-one", ("s1", "s2"), ("t1",), False),
        ("one-to-many", ("s1",), ("t1", "t2"), True),
        ("one-to-many", ("s1", "s2"), ("t1",), False),
        ("many-to-one", ("s1", "s2"), ("t1",), True),
        ("many-to-one", ("s1",), ("t1", "t2"), False),
        ("many-to-many", ("s1",), ("t1", "t2"), True),
        ("many-to-many", ("s1", "s2"), ("t1",), True),
        ("many-to-many", ("s1", "s2"), ("t1", "t2"), True),
    ],
)
def test_core_and_graph_runtimes_use_source_to_target_cardinality(
    cardinality: LinkCardinality,
    source_ids: tuple[str, ...],
    target_ids: tuple[str, ...],
    valid: bool,
) -> None:
    ontology, source_type, target_type, link = _definitions(cardinality)
    source_rows = tuple({"id": object_id, "join_key": "shared"} for object_id in source_ids)
    target_rows = tuple({"id": object_id, "join_key": "shared"} for object_id in target_ids)
    source_objects = materialize_object_type(source_type, source_rows)
    target_objects = materialize_object_type(target_type, target_rows)

    if valid:
        core_links = resolve_link_type(link, source_objects, target_objects)
        graph_snapshot = materialize_graph(
            ontology,
            {"Source": source_rows, "Target": target_rows},
        )
        graph_links = tuple((edge.source, edge.target) for edge in graph_snapshot.links)
        assert graph_links == core_links
    else:
        with pytest.raises(ValueError, match="cardinality"):
            resolve_link_type(link, source_objects, target_objects)
        with pytest.raises(GraphMaterializationError, match="cardinality"):
            materialize_graph(ontology, {"Source": source_rows, "Target": target_rows})


def test_core_and_graph_runtimes_join_typed_property_aliases_consistently() -> None:
    source = ObjectType(
        "Source",
        _ASSET,
        ("id",),
        (
            PropertyDefinition("id", "string", "id", required=True),
            PropertyDefinition("source_key", "integer", "source_column", required=True),
        ),
    )
    target = ObjectType(
        "Target",
        _ASSET,
        ("id",),
        (
            PropertyDefinition("id", "string", "id", required=True),
            PropertyDefinition("target_key", "integer", "target_column", required=True),
        ),
    )
    link = LinkType("related", "Source", "Target", "many-to-many", ("source_key",), ("target_key",))
    ontology = OntologyDefinition(OntologyId("aliases"), "1", "Aliases", (source, target), (link,))
    source_rows = ({"id": "s1", "source_column": 1},)
    target_rows = ({"id": "t1", "target_column": 1},)

    core_links = resolve_link_type(
        link,
        materialize_object_type(source, source_rows),
        materialize_object_type(target, target_rows),
    )
    graph = materialize_graph(ontology, {"Source": source_rows, "Target": target_rows})
    assert tuple((edge.source, edge.target) for edge in graph.links) == core_links
    assert len(core_links) == 1


def test_ontology_rejects_links_with_unknown_or_incompatible_properties() -> None:
    source = ObjectType(
        "Source",
        _ASSET,
        ("id",),
        (
            PropertyDefinition("id", "string", "id", required=True),
            PropertyDefinition("join", "integer", "join", required=True),
        ),
    )
    target = ObjectType(
        "Target",
        _ASSET,
        ("id",),
        (
            PropertyDefinition("id", "string", "id", required=True),
            PropertyDefinition("join", "string", "join", required=True),
        ),
    )
    incompatible = LinkType("related", "Source", "Target", "many-to-many", ("join",), ("join",))
    with pytest.raises(ValueError, match="incompatible property types"):
        OntologyDefinition(OntologyId("types"), "1", "Types", (source, target), (incompatible,))

    unknown = LinkType("related", "Source", "Target", "many-to-many", ("missing",), ("join",))
    with pytest.raises(ValueError, match="unknown property"):
        OntologyDefinition(OntologyId("unknown"), "1", "Unknown", (source, target), (unknown,))


def test_core_and_graph_runtimes_ignore_null_and_self_links_consistently() -> None:
    person = ObjectType(
        "Person",
        _ASSET,
        ("id",),
        (
            PropertyDefinition("id", "string", "id", required=True),
            PropertyDefinition("parent", "string", "parent_id"),
        ),
    )
    parent_link = LinkType("parent", "Person", "Person", "many-to-many", ("parent",), ("id",))
    self_link = LinkType("self", "Person", "Person", "many-to-many", ("id",), ("id",))
    ontology = OntologyDefinition(
        OntologyId("self-links"), "1", "Self links", (person,), (parent_link, self_link)
    )
    rows = ({"id": "one", "parent_id": None}, {"id": "two"})

    objects = materialize_object_type(person, rows)
    assert resolve_link_type(parent_link, objects, objects) == ()
    assert resolve_link_type(self_link, objects, objects) == ()
    graph = materialize_graph(ontology, {"Person": rows})
    assert graph.links == ()
