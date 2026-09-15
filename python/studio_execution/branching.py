"""Deterministic, fail-closed conditional branch evaluation.

This module evaluates only the small, JSON-shaped predicate vocabulary that can
be persisted in a workflow snapshot.  It does not execute arbitrary Python or
SQL and deliberately returns an explicit skip decision for a false branch.
Durable task-state integration remains a scheduler concern.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, TypeAlias

Scalar: TypeAlias = None | bool | int | float | str
Context: TypeAlias = Mapping[str, Scalar]


class UnsupportedBranchExpression(ValueError):
    """Raised when a branch expression is outside the persisted vocabulary."""


@dataclass(frozen=True, slots=True)
class BranchDecision:
    """The scheduler-visible outcome of evaluating one branch."""

    should_run: bool
    reason: str


def evaluate_branch(expression: object, context: Context) -> BranchDecision:
    """Evaluate a bounded predicate against an immutable scalar context.

    Supported forms are ``{"op": "equals|not_equals", "field": str,
    "value": scalar}``, ``{"op": "exists", "field": str}``, and boolean
    composition with ``all``, ``any`` and ``not``. Unknown keys, malformed
    values, nested context values and unknown operators fail closed.
    """

    result = _evaluate(expression, context)
    return BranchDecision(result, "predicate_true" if result else "predicate_false_skip")


def _evaluate(expression: object, context: Context) -> bool:
    if not isinstance(expression, Mapping):
        raise UnsupportedBranchExpression("branch expression must be an object")
    op = expression.get("op")
    if not isinstance(op, str):
        raise UnsupportedBranchExpression("branch expression op must be a string")
    allowed = {"op", "field", "value", "items"}
    if any(key not in allowed for key in expression):
        raise UnsupportedBranchExpression("branch expression contains unsupported keys")
    if op in {"equals", "not_equals", "exists"}:
        field = expression.get("field")
        if not isinstance(field, str) or not field or field != field.strip():
            raise UnsupportedBranchExpression("branch field must be a non-empty trimmed string")
        present = field in context
        if op == "exists":
            if "value" in expression or "items" in expression:
                raise UnsupportedBranchExpression("exists does not accept value or items")
            return present
        if "value" not in expression or not _is_scalar(expression["value"]):
            raise UnsupportedBranchExpression("comparison value must be a scalar")
        return present and ((context[field] == expression["value"]) == (op == "equals"))
    if op in {"all", "any"}:
        items = expression.get("items")
        if not isinstance(items, list) or not items:
            raise UnsupportedBranchExpression(f"{op} requires a non-empty items array")
        values = [_evaluate(item, context) for item in items]
        return all(values) if op == "all" else any(values)
    if op == "not":
        if set(expression) != {"op", "items"}:
            raise UnsupportedBranchExpression("not requires exactly one nested item")
        items = expression["items"]
        if not isinstance(items, list) or len(items) != 1:
            raise UnsupportedBranchExpression("not requires exactly one nested item")
        return not _evaluate(items[0], context)
    raise UnsupportedBranchExpression(f"unsupported branch operator: {op}")


def _is_scalar(value: object) -> bool:
    return value is None or isinstance(value, (bool, int, float, str))


__all__ = ("BranchDecision", "Context", "UnsupportedBranchExpression", "evaluate_branch")
