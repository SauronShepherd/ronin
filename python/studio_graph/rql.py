"""Parser for the explicit Ronin RQL v1 reference subset.

Grammar (case-insensitive keywords):

    MATCH <ObjectType>
      [WHERE <property> <op> <literal>]
      [TRAVERSE <LinkType> [OUT|IN] [DEPTH <1..8>]]
      RETURN <field>[,<field>...]
      [LIMIT <1..100000>]

`<op>` is one of = != > >= < <=. Literals are parsed as JSON scalars when
possible; otherwise they are treated as strings. This is intentionally a
bounded executable subset, not a claim of final RQL language completeness.
"""

from __future__ import annotations

import json
import re
import shlex

from .contracts import GraphFilter, GraphQueryIR, GraphScalar, GraphTraverse

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_OPERATORS = {
    "=": "eq",
    "!=": "ne",
    ">": "gt",
    ">=": "gte",
    "<": "lt",
    "<=": "lte",
}


class RqlSyntaxError(ValueError):
    """Raised when text is outside the supported RQL v1 subset."""


def _identifier(value: str, name: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise RqlSyntaxError(f"invalid {name}: {value!r}")
    return value


def _literal(token: str) -> GraphScalar:
    try:
        value = json.loads(token)
    except json.JSONDecodeError:
        value = token
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            raise RqlSyntaxError("RQL numeric literal must be finite")
        return value
    raise RqlSyntaxError("RQL literal must be a JSON scalar or string")


def parse_rql(text: str) -> GraphQueryIR:
    if not text or not text.strip():
        raise RqlSyntaxError("RQL query must be non-empty")
    try:
        tokens = shlex.split(text, posix=True)
    except ValueError as exc:
        raise RqlSyntaxError("RQL quoting is invalid") from exc
    if len(tokens) < 4 or tokens[0].upper() != "MATCH":
        raise RqlSyntaxError("RQL query must start with MATCH <ObjectType>")
    object_type = _identifier(tokens[1], "object type")
    index = 2
    filters: list[GraphFilter] = []
    traverse: GraphTraverse | None = None
    return_fields: tuple[str, ...] | None = None
    limit = 1000

    if index < len(tokens) and tokens[index].upper() == "WHERE":
        if index + 3 >= len(tokens):
            raise RqlSyntaxError("WHERE requires property, operator, and literal")
        property_name = _identifier(tokens[index + 1], "filter property")
        operator_token = tokens[index + 2]
        operator = _OPERATORS.get(operator_token)
        if operator is None:
            raise RqlSyntaxError(f"unsupported RQL filter operator: {operator_token}")
        filters.append(GraphFilter(property_name, operator, _literal(tokens[index + 3])))  # type: ignore[arg-type]
        index += 4

    if index < len(tokens) and tokens[index].upper() == "TRAVERSE":
        if index + 1 >= len(tokens):
            raise RqlSyntaxError("TRAVERSE requires a link type")
        link_type = _identifier(tokens[index + 1], "link type")
        index += 2
        direction = "out"
        depth = 1
        if index < len(tokens) and tokens[index].upper() in {"OUT", "IN"}:
            direction = tokens[index].lower()
            index += 1
        if index < len(tokens) and tokens[index].upper() == "DEPTH":
            if index + 1 >= len(tokens):
                raise RqlSyntaxError("DEPTH requires an integer")
            try:
                depth = int(tokens[index + 1])
            except ValueError as exc:
                raise RqlSyntaxError("DEPTH must be an integer") from exc
            index += 2
        traverse = GraphTraverse(link_type, direction, depth)  # type: ignore[arg-type]

    if index >= len(tokens) or tokens[index].upper() != "RETURN":
        raise RqlSyntaxError("RQL query requires RETURN")
    index += 1
    if index >= len(tokens):
        raise RqlSyntaxError("RETURN requires at least one field")
    field_tokens: list[str] = []
    while index < len(tokens) and tokens[index].upper() != "LIMIT":
        field_tokens.append(tokens[index])
        index += 1
    fields_raw = "".join(field_tokens)
    fields = tuple(_identifier(value, "return field") for value in fields_raw.split(",") if value)
    if not fields:
        raise RqlSyntaxError("RETURN requires at least one field")
    if len(fields) != len(set(fields)):
        raise RqlSyntaxError("RETURN fields must be unique")
    return_fields = fields

    if index < len(tokens):
        if tokens[index].upper() != "LIMIT" or index + 1 >= len(tokens):
            raise RqlSyntaxError("unexpected tokens after RETURN fields")
        try:
            limit = int(tokens[index + 1])
        except ValueError as exc:
            raise RqlSyntaxError("LIMIT must be an integer") from exc
        index += 2
    if index != len(tokens):
        raise RqlSyntaxError("unexpected trailing RQL tokens")

    return GraphQueryIR(
        object_type,
        tuple(filters),
        traverse,
        return_fields,
        limit,
    )


__all__ = ("RqlSyntaxError", "parse_rql")
