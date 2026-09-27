"""Safe, provider-neutral SQL join contracts for semantic models."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from .contracts import SemanticDimension, SemanticMeasure, SemanticModel

JoinType = Literal["inner", "left"]


def _identifier(value: str, name: str) -> str:
    if not value or value != value.strip() or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"{name} must be a portable identifier")
    return value


@dataclass(frozen=True, slots=True)
class SemanticJoin:
    left_column: str
    right_column: str
    join_type: JoinType = "inner"

    def __post_init__(self) -> None:
        _identifier(self.left_column, "join left column")
        _identifier(self.right_column, "join right column")
        if self.join_type not in {"inner", "left"}:
            raise ValueError("unsupported semantic join type")


def compile_join_sql(left: SemanticModel, right: SemanticModel, join: SemanticJoin) -> str:
    """Compile a deterministic, identifier-only two-model join fragment."""
    left_alias = _identifier(left.id, "left model id")
    right_alias = _identifier(right.id, "right model id")
    if left_alias == right_alias:
        raise ValueError("semantic join model ids must be distinct")
    keyword = "LEFT JOIN" if join.join_type == "left" else "JOIN"

    def quote(value: str) -> str:
        return '"' + value.replace('"', '""') + '"'

    return (
        f"FROM {quote(left.source)} AS {quote(left_alias)} {keyword} "
        f"{quote(right.source)} AS {quote(right_alias)} ON "
        f"{quote(left_alias)}.{quote(join.left_column)} = "
        f"{quote(right_alias)}.{quote(join.right_column)}"
    )


def compile_join_query(left: SemanticModel, right: SemanticModel, join: SemanticJoin) -> str:
    """Compile a bounded two-model projection using only declared model columns."""
    left_alias = _identifier(left.id, "left model id")
    right_alias = _identifier(right.id, "right model id")
    if left_alias == right_alias:
        raise ValueError("semantic join model ids must be distinct")

    def quote(value: str) -> str:
        return '"' + value.replace('"', '""') + '"'

    def projections(model: SemanticModel, alias: str) -> list[str]:
        items: tuple[SemanticDimension | SemanticMeasure, ...] = (
            *model.dimensions,
            *model.measures,
        )
        return [
            f"{quote(alias)}.{quote(item.column)} AS {quote(f'{alias}_{item.name}')}"
            for item in items
            if item.column is not None
        ]

    columns = projections(left, left_alias) + projections(right, right_alias)
    if not columns:
        raise ValueError("semantic join requires at least one declared model column")
    return "SELECT " + ", ".join(columns) + " " + compile_join_sql(left, right, join)


def compile_join_chain(
    base: SemanticModel,
    steps: Sequence[tuple[SemanticModel, SemanticJoin]],
) -> str:
    """Compile a bounded left-deep chain of deterministic semantic joins."""
    if not steps or len(steps) > 8:
        raise ValueError("semantic join chain must contain between 1 and 8 steps")
    models = [base, *(model for model, _ in steps)]
    aliases = [_identifier(model.id, "semantic model id") for model in models]
    if len(set(aliases)) != len(aliases):
        raise ValueError("semantic join model ids must be distinct")

    def quote(value: str) -> str:
        return '"' + value.replace('"', '""') + '"'

    columns: list[str] = []
    for model, alias in zip(models, aliases, strict=True):
        items: tuple[SemanticDimension | SemanticMeasure, ...] = (
            *model.dimensions,
            *model.measures,
        )
        columns.extend(
            f"{quote(alias)}.{quote(item.column)} AS {quote(f'{alias}_{item.name}')}"
            for item in items
            if item.column is not None
        )
    if not columns:
        raise ValueError("semantic join chain requires declared model columns")
    from_sql = f"FROM {quote(base.source)} AS {quote(aliases[0])}"
    for index, (model, join) in enumerate(steps, start=1):
        keyword = "LEFT JOIN" if join.join_type == "left" else "JOIN"
        from_sql += (
            f" {keyword} {quote(model.source)} AS {quote(aliases[index])} ON "
            f"{quote(aliases[index - 1])}.{quote(join.left_column)} = "
            f"{quote(aliases[index])}.{quote(join.right_column)}"
        )
    return "SELECT " + ", ".join(columns) + " " + from_sql


__all__ = (
    "JoinType",
    "SemanticJoin",
    "compile_join_chain",
    "compile_join_query",
    "compile_join_sql",
)
