"""Deterministic, fail-closed conditional branch evaluation.

This module evaluates only the small, JSON-shaped predicate vocabulary that can
be persisted in a workflow snapshot.  It does not execute arbitrary Python or
SQL and deliberately returns an explicit skip decision for a false branch.
Durable task-state integration remains a scheduler concern.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeAlias

from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.canonical_json import encode as encode_canonical_json

Scalar: TypeAlias = None | bool | int | float | str
Context: TypeAlias = Mapping[str, Scalar]


class UnsupportedBranchExpression(ValueError):
    """Raised when a branch expression is outside the persisted vocabulary."""


@dataclass(frozen=True, slots=True)
class BranchDecision:
    """The scheduler-visible outcome of evaluating one branch."""

    should_run: bool
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.should_run, bool):
            raise TypeError("branch decision should_run must be boolean")
        if not self.reason or self.reason != self.reason.strip():
            raise ValueError("branch decision reason must be non-empty and trimmed")

    def to_payload(self) -> dict[str, object]:
        return {"version": 1, "should_run": self.should_run, "reason": self.reason}

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode()

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.to_json().encode()).hexdigest()

    @classmethod
    def from_payload(cls, value: object) -> BranchDecision:
        if not isinstance(value, Mapping) or set(value) != {"version", "should_run", "reason"}:
            raise ValueError("branch decision has invalid shape")
        if value["version"] != 1:
            raise ValueError("unsupported branch decision version")
        if not isinstance(value["should_run"], bool) or not isinstance(value["reason"], str):
            raise TypeError("branch decision fields have invalid types")
        return cls(value["should_run"], value["reason"])

    @classmethod
    def from_json(cls, payload: str) -> BranchDecision:
        return cls.from_payload(decode_canonical_json(payload))


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
