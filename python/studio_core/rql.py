"""Small, bounded RQL query surface over a materialized knowledge graph."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .ontology import KnowledgeGraph, KnowledgeObject

_SELECT = re.compile(
    r"^SELECT\s+(?P<type>[A-Za-z_][\w.-]*)(?:\s+WHERE\s+(?P<field>[A-Za-z_][\w.-]*)\s*=\s*'(?P<value>[^']*)')?(?:\s+LIMIT\s+(?P<limit>\d+))?$",
    re.I,
)


@dataclass(frozen=True, slots=True)
class RqlResult:
    objects: tuple[KnowledgeObject, ...]


def execute_rql(query: str, graph: KnowledgeGraph, *, max_limit: int = 10_000) -> RqlResult:
    """Execute the supported read-only SELECT subset with strict bounds."""
    if not query or len(query) > 2_000:
        raise ValueError("RQL query must be non-empty and at most 2000 characters")
    match = _SELECT.fullmatch(query.strip())
    if match is None:
        raise ValueError("unsupported RQL; expected SELECT Type [WHERE field = 'value'] [LIMIT n]")
    limit = int(match.group("limit") or max_limit)
    if limit < 1 or limit > max_limit:
        raise ValueError("RQL limit is outside the configured bound")
    field, value = match.group("field"), match.group("value")
    objects = graph.objects_of_type(match.group("type"), limit=limit)
    if field is not None:
        objects = tuple(item for item in objects if dict(item.properties).get(field) == value)
    return RqlResult(objects=objects[:limit])


__all__ = ["RqlResult", "execute_rql"]
