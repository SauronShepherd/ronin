"""Provider-neutral Graph IR execution with a native persistent reference provider."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from studio_core.ontology import KnowledgeObjectRef, OntologyId

from .contracts import (
    GraphFilter,
    GraphObject,
    GraphQueryIR,
    GraphQueryResult,
    GraphScalar,
)


@runtime_checkable
class GraphReadStore(Protocol):
    def scan_objects(
        self,
        ontology_id: OntologyId,
        ontology_version: str,
        object_type: str,
    ) -> tuple[GraphObject, ...]: ...

    def neighbors(
        self,
        ontology_id: OntologyId,
        ontology_version: str,
        ref: KnowledgeObjectRef,
        *,
        link_type: str,
        direction: str,
    ) -> tuple[GraphObject, ...]: ...


@runtime_checkable
class GraphQueryProvider(Protocol):
    def execute(self, query: GraphQueryIR) -> GraphQueryResult: ...


def _compare(left: GraphScalar, filter_: GraphFilter) -> bool:
    right = filter_.value
    if filter_.operator == "eq":
        return left == right
    if filter_.operator == "ne":
        return left != right
    if left is None or right is None:
        return False
    if isinstance(left, bool) or isinstance(right, bool):
        return False
    numeric = isinstance(left, (int, float)) and isinstance(right, (int, float))
    textual = isinstance(left, str) and isinstance(right, str)
    if not numeric and not textual:
        return False
    if filter_.operator == "gt":
        return left > right  # type: ignore[operator]
    if filter_.operator == "gte":
        return left >= right  # type: ignore[operator]
    if filter_.operator == "lt":
        return left < right  # type: ignore[operator]
    if filter_.operator == "lte":
        return left <= right  # type: ignore[operator]
    raise AssertionError(f"unsupported graph filter operator: {filter_.operator}")


def _matches(item: GraphObject, filters: tuple[GraphFilter, ...]) -> bool:
    properties = dict(item.properties)
    for filter_ in filters:
        if filter_.property_name not in properties:
            return False
        if not _compare(properties[filter_.property_name], filter_):
            return False
    return True


def _key_text(ref: KnowledgeObjectRef) -> str:
    return ",".join(f"{key}={value}" for key, value in ref.key)


class NativeGraphProvider:
    """Execute bounded Graph IR against one materialized ontology snapshot."""

    def __init__(
        self,
        store: GraphReadStore,
        ontology_id: OntologyId,
        ontology_version: str,
    ) -> None:
        self._store = store
        self._ontology_id = ontology_id
        self._ontology_version = ontology_version

    def execute(self, query: GraphQueryIR) -> GraphQueryResult:
        initial = tuple(
            item
            for item in self._store.scan_objects(
                self._ontology_id,
                self._ontology_version,
                query.object_type,
            )
            if _matches(item, query.filters)
        )
        selected: dict[KnowledgeObjectRef, GraphObject]
        if query.traverse is None:
            selected = {item.ref: item for item in initial}
        else:
            visited = {item.ref for item in initial}
            frontier = {item.ref: item for item in initial}
            reached: dict[KnowledgeObjectRef, GraphObject] = {}
            for _depth in range(query.traverse.depth):
                next_frontier: dict[KnowledgeObjectRef, GraphObject] = {}
                for item in frontier.values():
                    for neighbor in self._store.neighbors(
                        self._ontology_id,
                        self._ontology_version,
                        item.ref,
                        link_type=query.traverse.link_type,
                        direction=query.traverse.direction,
                    ):
                        if neighbor.ref in visited:
                            continue
                        visited.add(neighbor.ref)
                        reached[neighbor.ref] = neighbor
                        next_frontier[neighbor.ref] = neighbor
                frontier = next_frontier
                if not frontier:
                    break
            selected = reached

        rows: list[tuple[tuple[str, GraphScalar], ...]] = []
        for item in sorted(selected.values(), key=lambda value: value.ref):
            properties = dict(item.properties)
            row: list[tuple[str, GraphScalar]] = []
            for field in query.return_fields:
                if field == "_type":
                    row.append((field, item.ref.object_type))
                elif field == "_key":
                    row.append((field, _key_text(item.ref)))
                elif field in properties:
                    row.append((field, properties[field]))
                else:
                    raise KeyError(
                        f"return field {field!r} is absent from object type {item.ref.object_type}"
                    )
            rows.append(tuple(row))
            if len(rows) >= query.limit:
                break
        return GraphQueryResult(tuple(rows))


__all__ = ("GraphQueryProvider", "GraphReadStore", "NativeGraphProvider")
