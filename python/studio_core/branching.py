"""Bounded, fail-closed branch evaluation shared by scheduler adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeAlias

from .canonical_json import decode, encode

Scalar: TypeAlias = None | bool | int | float | str


@dataclass(frozen=True, slots=True)
class BranchDecision:
    should_run: bool
    reason: str

    def to_payload(self) -> dict[str, object]:
        return {"version": 1, "should_run": self.should_run, "reason": self.reason}

    def to_json(self) -> str:
        return encode(self.to_payload()).decode()

    @classmethod
    def from_json(cls, payload: str) -> BranchDecision:
        value = decode(payload)
        if not isinstance(value, Mapping) or value.get("version") != 1:
            raise ValueError("invalid branch decision")
        should_run = value.get("should_run")
        reason = value.get("reason")
        if not isinstance(should_run, bool) or not isinstance(reason, str) or not reason.strip():
            raise ValueError("invalid branch decision fields")
        return cls(should_run, reason)


def evaluate_branch(expression: object, context: Mapping[str, Scalar]) -> BranchDecision:
    if not isinstance(expression, Mapping) or not isinstance(expression.get("op"), str):
        raise ValueError("unsupported branch expression")
    op = expression["op"]
    if op in {"equals", "not_equals", "exists"}:
        field = expression.get("field")
        if not isinstance(field, str) or not field.strip():
            raise ValueError("branch field must be non-empty")
        if op == "exists":
            result = field in context
        else:
            value = expression.get("value")
            if not (value is None or isinstance(value, (bool, int, float, str))):
                raise ValueError("branch value must be scalar")
            result = field in context and ((context[field] == value) == (op == "equals"))
    else:
        items = expression.get("items")
        if op in {"all", "any"} and isinstance(items, list) and items:
            values = [evaluate_branch(item, context).should_run for item in items]
            result = all(values) if op == "all" else any(values)
        elif op == "not" and isinstance(items, list) and len(items) == 1:
            result = not evaluate_branch(items[0], context).should_run
        else:
            raise ValueError("unsupported branch expression")
    return BranchDecision(result, "predicate_true" if result else "predicate_false_skip")
