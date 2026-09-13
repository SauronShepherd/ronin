"""Materialized knowledge-graph and provider-neutral Graph IR contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from studio_core.ontology import KnowledgeObjectRef, OntologyId

GraphScalar: TypeAlias = None | bool | int | float | str
FilterOperator: TypeAlias = Literal["eq", "ne", "gt", "gte", "lt", "lte"]
TraverseDirection: TypeAlias = Literal["out", "in"]


def _text(value: str, name: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    return value


@dataclass(frozen=True, slots=True)
class GraphObject:
    ref: KnowledgeObjectRef
    properties: tuple[tuple[str, GraphScalar], ...]

    def __post_init__(self) -> None:
        properties = tuple(sorted(self.properties, key=lambda item: item[0]))
        names = [name for name, _ in properties]
        if len(names) != len(set(names)):
            raise ValueError("graph object property names must be unique")
        for name, value in properties:
            _text(name, "graph property name")
            if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
                raise ValueError("graph property floats must be finite")
            if value is not None and not isinstance(value, (bool, int, float, str)):
                raise TypeError("graph property values must be scalar")
        object.__setattr__(self, "properties", properties)

    def property(self, name: str) -> GraphScalar:
        for key, value in self.properties:
            if key == name:
                return value
        raise KeyError(name)


@dataclass(frozen=True, order=True, slots=True)
class GraphLink:
    link_type: str
    source: KnowledgeObjectRef
    target: KnowledgeObjectRef

    def __post_init__(self) -> None:
        _text(self.link_type, "graph link type")
        if self.source == self.target:
            raise ValueError("graph link source and target must differ")


@dataclass(frozen=True, slots=True)
class GraphSnapshot:
    ontology_id: OntologyId
    ontology_version: str
    objects: tuple[GraphObject, ...]
    links: tuple[GraphLink, ...] = ()

    def __post_init__(self) -> None:
        _text(self.ontology_version, "graph ontology version")
        objects = tuple(sorted(self.objects, key=lambda item: item.ref))
        refs = [item.ref for item in objects]
        if len(refs) != len(set(refs)):
            raise ValueError("graph snapshot object refs must be unique")
        known = set(refs)
        links = tuple(sorted(self.links))
        if len(links) != len(set(links)):
            raise ValueError("graph snapshot links must be unique")
        if any(link.source not in known or link.target not in known for link in links):
            raise ValueError("graph snapshot links must reference known objects")
        object.__setattr__(self, "objects", objects)
        object.__setattr__(self, "links", links)


@dataclass(frozen=True, slots=True)
class GraphFilter:
    property_name: str
    operator: FilterOperator
    value: GraphScalar

    def __post_init__(self) -> None:
        _text(self.property_name, "graph filter property")
        if self.operator not in {"eq", "ne", "gt", "gte", "lt", "lte"}:
            raise ValueError("unsupported graph filter operator")


@dataclass(frozen=True, slots=True)
class GraphTraverse:
    link_type: str
    direction: TraverseDirection = "out"
    depth: int = 1

    def __post_init__(self) -> None:
        _text(self.link_type, "graph traverse link_type")
        if self.direction not in {"out", "in"}:
            raise ValueError("graph traverse direction must be out or in")
        if self.depth < 1 or self.depth > 8:
            raise ValueError("graph traverse depth must be between 1 and 8")


@dataclass(frozen=True, slots=True)
class GraphQueryIR:
    object_type: str
    filters: tuple[GraphFilter, ...] = ()
    traverse: GraphTraverse | None = None
    return_fields: tuple[str, ...] = ()
    limit: int = 1000

    def __post_init__(self) -> None:
        _text(self.object_type, "graph query object_type")
        fields = tuple(self.return_fields)
        if len(fields) != len(set(fields)):
            raise ValueError("graph query return fields must be unique")
        for field in fields:
            _text(field, "graph return field")
        object.__setattr__(self, "filters", tuple(self.filters))
        object.__setattr__(self, "return_fields", fields)
        if self.limit < 1 or self.limit > 100_000:
            raise ValueError("graph query limit must be between 1 and 100000")


@dataclass(frozen=True, slots=True)
class GraphQueryResult:
    rows: tuple[tuple[tuple[str, GraphScalar], ...], ...]

    def __post_init__(self) -> None:
        canonical: list[tuple[tuple[str, GraphScalar], ...]] = []
        for row in self.rows:
            pairs = tuple(sorted(row, key=lambda item: item[0]))
            names = [name for name, _ in pairs]
            if len(names) != len(set(names)):
                raise ValueError("graph result row fields must be unique")
            canonical.append(pairs)
        object.__setattr__(self, "rows", tuple(canonical))


__all__ = (
    "FilterOperator",
    "GraphFilter",
    "GraphLink",
    "GraphObject",
    "GraphQueryIR",
    "GraphQueryResult",
    "GraphScalar",
    "GraphSnapshot",
    "GraphTraverse",
    "TraverseDirection",
)
