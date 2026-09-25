"""Provider-neutral graph query port and bounded local reference executor."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .ontology import KnowledgeGraph
from .rql import RqlQuery, RqlResult, execute_rql


@runtime_checkable
class GraphQueryExecutor(Protocol):
    """Read-only graph execution boundary for local and remote providers."""

    @property
    def capabilities(self) -> frozenset[str]: ...

    def execute(self, query: RqlQuery, *, max_limit: int = 10_000) -> RqlResult: ...


class LocalGraphQueryExecutor:
    """Reference executor over one materialized graph view."""

    capabilities = frozenset({"read", "where", "traverse", "join", "bounded"})

    def __init__(self, graph: KnowledgeGraph) -> None:
        self._graph = graph

    def execute(self, query: RqlQuery, *, max_limit: int = 10_000) -> RqlResult:
        if not isinstance(query, RqlQuery):
            raise TypeError("graph executor requires an RqlQuery AST")
        if max_limit < 1 or max_limit > 100_000:
            raise ValueError("graph max_limit must be between 1 and 100000")
        limit = query.limit or max_limit
        if limit > max_limit:
            raise ValueError("RQL limit is outside the executor bound")
        return execute_rql(_render_query(query), self._graph, max_limit=max_limit)


def _render_query(query: RqlQuery) -> str:
    rendered = f"SELECT {query.source_type}"
    if query.where_field is not None:
        rendered += f" WHERE {query.where_field} = '{query.where_value}'"
    if query.traverse_type is not None:
        rendered += f" TRAVERSE {query.traverse_type}"
    if query.join_type is not None:
        rendered += f" JOIN {query.join_type} ON {query.join_left} = {query.join_right}"
    if query.limit is not None:
        rendered += f" LIMIT {query.limit}"
    return rendered


__all__ = ("GraphQueryExecutor", "LocalGraphQueryExecutor")
