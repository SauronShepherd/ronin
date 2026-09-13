"""Materialize ontology objects and virtual links from governed source rows."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import cast

from studio_core.ontology import KnowledgeObjectRef, LinkType, ObjectType, OntologyDefinition

from .contracts import GraphLink, GraphObject, GraphScalar, GraphSnapshot


class GraphMaterializationError(ValueError):
    """Raised when source rows cannot satisfy declared ontology semantics."""


def _scalar(value: object, *, field: str) -> GraphScalar:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise GraphMaterializationError(f"field {field!r} contains non-finite float")
        return value
    raise GraphMaterializationError(f"field {field!r} is not a supported scalar value")


def _object_ref(definition: ObjectType, row: Mapping[str, object]) -> KnowledgeObjectRef:
    pairs: list[tuple[str, str]] = []
    for source_field in definition.key_fields:
        if source_field not in row:
            raise GraphMaterializationError(
                f"object type {definition.name} row is missing key field {source_field!r}"
            )
        value = row[source_field]
        if value is None:
            raise GraphMaterializationError(
                f"object type {definition.name} key field {source_field!r} is null"
            )
        scalar = _scalar(value, field=source_field)
        pairs.append((source_field, str(scalar)))
    return KnowledgeObjectRef(definition.name, tuple(pairs))


def _graph_object(definition: ObjectType, row: Mapping[str, object]) -> GraphObject:
    properties: list[tuple[str, GraphScalar]] = []
    for prop in definition.properties:
        if prop.source_field not in row:
            if prop.required:
                raise GraphMaterializationError(
                    f"required property {definition.name}.{prop.name} source field is missing"
                )
            value: GraphScalar = None
        else:
            raw = row[prop.source_field]
            if raw is None and prop.required:
                raise GraphMaterializationError(
                    f"required property {definition.name}.{prop.name} is null"
                )
            value = _scalar(raw, field=prop.source_field)
        properties.append((prop.name, value))
    return GraphObject(_object_ref(definition, row), tuple(properties))


def _join_key(row: Mapping[str, object], fields: tuple[str, ...], *, link_name: str) -> tuple[str, ...]:
    result: list[str] = []
    for field in fields:
        if field not in row:
            raise GraphMaterializationError(
                f"link {link_name} source row is missing join field {field!r}"
            )
        value = row[field]
        if value is None:
            return ()
        result.append(str(_scalar(value, field=field)))
    return tuple(result)


def _validate_cardinality(link: LinkType, links: Sequence[GraphLink]) -> None:
    sources: dict[KnowledgeObjectRef, int] = defaultdict(int)
    targets: dict[KnowledgeObjectRef, int] = defaultdict(int)
    for edge in links:
        sources[edge.source] += 1
        targets[edge.target] += 1
    if link.cardinality == "one-to-one":
        if any(value > 1 for value in sources.values()) or any(value > 1 for value in targets.values()):
            raise GraphMaterializationError(f"link {link.name} violates one-to-one cardinality")
    elif link.cardinality == "one-to-many":
        if any(value > 1 for value in targets.values()):
            raise GraphMaterializationError(f"link {link.name} violates one-to-many cardinality")
    elif link.cardinality == "many-to-one":
        if any(value > 1 for value in sources.values()):
            raise GraphMaterializationError(f"link {link.name} violates many-to-one cardinality")


def materialize_graph(
    ontology: OntologyDefinition,
    rows_by_object_type: Mapping[str, Sequence[Mapping[str, object]]],
) -> GraphSnapshot:
    """Materialize a deterministic graph for ontology object types and virtual links."""

    object_definitions = {item.name: item for item in ontology.object_types}
    unexpected = set(rows_by_object_type) - set(object_definitions)
    if unexpected:
        raise GraphMaterializationError(
            f"source rows provided for unknown ontology object types: {sorted(unexpected)}"
        )

    objects: list[GraphObject] = []
    source_rows: dict[str, list[tuple[KnowledgeObjectRef, Mapping[str, object]]]] = {}
    for object_type in ontology.object_types:
        rows = rows_by_object_type.get(object_type.name, ())
        materialized: list[tuple[KnowledgeObjectRef, Mapping[str, object]]] = []
        seen: set[KnowledgeObjectRef] = set()
        for row in rows:
            graph_object = _graph_object(object_type, row)
            if graph_object.ref in seen:
                raise GraphMaterializationError(
                    f"duplicate object key for {object_type.name}: {graph_object.ref.key}"
                )
            seen.add(graph_object.ref)
            objects.append(graph_object)
            materialized.append((graph_object.ref, row))
        source_rows[object_type.name] = materialized

    links: list[GraphLink] = []
    for link in ontology.link_types:
        if link.backing_asset is not None:
            raise GraphMaterializationError(
                f"link {link.name} uses a backing asset and requires an explicit link-materializer adapter"
            )
        source_entries = source_rows[link.source_type]
        target_entries = source_rows[link.target_type]
        targets_by_key: dict[tuple[str, ...], list[KnowledgeObjectRef]] = defaultdict(list)
        for target_ref, target_row in target_entries:
            key = _join_key(target_row, link.target_fields, link_name=link.name)
            if key:
                targets_by_key[key].append(target_ref)
        materialized_links: list[GraphLink] = []
        for source_ref, source_row in source_entries:
            key = _join_key(source_row, link.source_fields, link_name=link.name)
            if not key:
                continue
            for target_ref in targets_by_key.get(key, ()):
                if source_ref == target_ref:
                    continue
                materialized_links.append(GraphLink(link.name, source_ref, target_ref))
        materialized_links = list(sorted(set(materialized_links)))
        _validate_cardinality(link, materialized_links)
        links.extend(materialized_links)

    return GraphSnapshot(
        ontology.id,
        ontology.version,
        tuple(objects),
        tuple(links),
    )


__all__ = ("GraphMaterializationError", "materialize_graph")
