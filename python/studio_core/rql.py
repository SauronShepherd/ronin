"""Small, bounded RQL query surface over a materialized knowledge graph."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from .canonical_json import encode as encode_canonical_json
from .ontology import KnowledgeGraph, KnowledgeObject

_SELECT = re.compile(
    r"^SELECT\s+(?P<type>[A-Za-z_][\w.-]*)"
    r"(?:\s+WHERE\s+(?P<field>[A-Za-z_][\w.-]*)\s*=\s*'(?P<value>[^']*)')?"
    r"(?:\s+TRAVERSE\s+(?P<target>[A-Za-z_][\w.-]*))?"
    r"(?:\s+JOIN\s+(?P<join_type>[A-Za-z_][\w.-]*)\s+ON\s+"
    r"(?P<join_left>[A-Za-z_][\w.-]*)\s*=\s*(?P<join_right>[A-Za-z_][\w.-]*))?"
    r"(?:\s+LIMIT\s+(?P<limit>\d+))?$",
    re.I,
)


@dataclass(frozen=True, slots=True)
class RqlResult:
    objects: tuple[KnowledgeObject, ...]


@dataclass(frozen=True, slots=True)
class RqlQuery:
    """Frozen RQL v1 AST used by local and future provider executors."""

    source_type: str
    where_field: str | None = None
    where_value: str | None = None
    traverse_type: str | None = None
    join_type: str | None = None
    join_left: str | None = None
    join_right: str | None = None
    limit: int | None = None

    def to_data(self) -> dict[str, object]:
        return {
            "version": 1,
            "source_type": self.source_type,
            "where": None
            if self.where_field is None
            else {"field": self.where_field, "value": self.where_value},
            "traverse_type": self.traverse_type,
            "join": None
            if self.join_type is None
            else {
                "type": self.join_type,
                "left": self.join_left,
                "right": self.join_right,
            },
            "limit": self.limit,
        }

    def canonical_json(self) -> str:
        return encode_canonical_json(self.to_data()).decode()

    @classmethod
    def from_data(cls, value: Mapping[str, object]) -> RqlQuery:
        expected = {
            "version",
            "source_type",
            "where",
            "traverse_type",
            "join",
            "limit",
        }
        if set(value) != expected:
            raise ValueError("RQL AST keys do not match version 1")
        if value["version"] != 1:
            raise ValueError("unsupported RQL AST version")
        source_type = _identifier(value["source_type"], "RQL AST source_type")
        where_value = value["where"]
        where_field = None
        literal = None
        if where_value is not None:
            where = _as_mapping(where_value, "RQL AST where")
            if set(where) != {"field", "value"}:
                raise ValueError("RQL AST where keys are invalid")
            where_field = _identifier(where["field"], "RQL AST where.field")
            literal = _as_text(where["value"], "RQL AST where.value")
        join_value = value["join"]
        join_type = join_left = join_right = None
        if join_value is not None:
            join = _as_mapping(join_value, "RQL AST join")
            if set(join) != {"type", "left", "right"}:
                raise ValueError("RQL AST join keys are invalid")
            join_type = _identifier(join["type"], "RQL AST join.type")
            join_left = _identifier(join["left"], "RQL AST join.left")
            join_right = _identifier(join["right"], "RQL AST join.right")
        limit = value["limit"]
        if limit is not None and (
            not isinstance(limit, int) or isinstance(limit, bool) or limit < 1
        ):
            raise ValueError("RQL AST limit must be a positive integer or null")
        return cls(
            source_type,
            where_field,
            literal,
            None
            if value["traverse_type"] is None
            else _identifier(value["traverse_type"], "RQL AST traverse_type"),
            join_type,
            join_left,
            join_right,
            cast(int | None, limit),
        )


def _as_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise TypeError(f"{name} must be an object")
    return cast(Mapping[str, object], value)


def _as_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty trimmed text")
    return value


def _optional_text(value: object, name: str) -> str | None:
    return None if value is None else _as_text(value, name)


def _identifier(value: object, name: str) -> str:
    text = _as_text(value, name)
    if re.fullmatch(r"[A-Za-z_][\w.-]*", text) is None:
        raise ValueError(f"{name} must be a portable identifier")
    return text


def parse_rql(query: str) -> RqlQuery:
    if not isinstance(query, str) or not query or len(query) > 2_000:
        raise ValueError("RQL query must be non-empty and at most 2000 characters")
    match = _SELECT.fullmatch(query.strip())
    if match is None:
        raise ValueError(
            "unsupported RQL; expected SELECT Type [WHERE field = 'value'] "
            "[TRAVERSE TargetType] [JOIN Type ON field = field] [LIMIT n]"
        )
    raw_limit = match.group("limit")
    return RqlQuery(
        source_type=match.group("type"),
        where_field=match.group("field"),
        where_value=match.group("value"),
        traverse_type=match.group("target"),
        join_type=match.group("join_type"),
        join_left=match.group("join_left"),
        join_right=match.group("join_right"),
        limit=None if raw_limit is None else int(raw_limit),
    )


def execute_rql(query: str, graph: KnowledgeGraph, *, max_limit: int = 10_000) -> RqlResult:
    """Execute the supported read-only SELECT subset with strict bounds."""
    parsed = parse_rql(query)
    limit = parsed.limit or max_limit
    if limit < 1 or limit > max_limit:
        raise ValueError("RQL limit is outside the configured bound")
    field, value = parsed.where_field, parsed.where_value
    source_type = parsed.source_type
    objects = graph.objects_of_type(source_type, limit=limit)
    if field is not None:
        objects = tuple(item for item in objects if dict(item.properties).get(field) == value)
    target_type = parsed.traverse_type
    if target_type is not None:
        refs = {
            neighbor
            for item in objects
            for neighbor in graph.neighbors(item.ref, limit=limit)
            if neighbor.object_type == target_type
        }
        by_ref = {item.ref: item for item in graph.objects if item.ref in refs}
        objects = tuple(by_ref[ref] for ref in sorted(refs) if ref in by_ref)
    join_type = parsed.join_type
    if join_type is not None:
        left_field, right_field = parsed.join_left, parsed.join_right
        if left_field is None or right_field is None:
            raise ValueError("RQL join requires both field names")
        target_objects = graph.objects_of_type(join_type, limit=max_limit)
        left_values = {dict(item.properties).get(left_field) for item in objects}
        objects = tuple(
            item for item in target_objects if dict(item.properties).get(right_field) in left_values
        )
    return RqlResult(objects=objects[:limit])


__all__ = ["RqlQuery", "RqlResult", "execute_rql", "parse_rql"]
