"""Bounded expression evaluator for custom quality predicates."""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, TimeoutError


class PredicateSandboxError(ValueError):
    """Raised when a custom predicate is invalid or exceeds a sandbox limit."""


_ALLOWED_NODES = {
    ast.Expression,
    ast.BoolOp,
    ast.Compare,
    ast.Constant,
    ast.Dict,
    ast.List,
    ast.Name,
    ast.Subscript,
    ast.Load,
    ast.Store,
    ast.And,
    ast.Or,
    ast.Not,
    ast.UnaryOp,
    ast.Eq,
    ast.NotEq,
    ast.Gt,
    ast.GtE,
    ast.Lt,
    ast.LtE,
    ast.In,
    ast.NotIn,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.USub,
    ast.Call,
    ast.comprehension,
    ast.GeneratorExp,
}
_SAFE_BUILTINS = {"all": all, "any": any, "len": len, "max": max, "min": min, "sum": sum}


def _validate(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if type(node) not in _ALLOWED_NODES:
            raise PredicateSandboxError(f"unsupported predicate syntax: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise PredicateSandboxError("dunder names are not allowed")
        if isinstance(node, ast.Call) and (
            not isinstance(node.func, ast.Name) or node.func.id not in _SAFE_BUILTINS
        ):
            raise PredicateSandboxError("only bounded aggregate functions are allowed")


def evaluate_python_predicate(
    expression: str,
    rows: Sequence[Mapping[str, object]],
    *,
    timeout_seconds: float = 0.25,
    max_source_chars: int = 4_000,
    max_rows: int = 10_000,
) -> bool:
    if not expression or len(expression) > max_source_chars:
        raise PredicateSandboxError("predicate source exceeds configured limit")
    if timeout_seconds <= 0 or timeout_seconds > 10:
        raise PredicateSandboxError("predicate timeout is outside configured bounds")
    if len(rows) > max_rows:
        raise PredicateSandboxError("predicate input exceeds configured row limit")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise PredicateSandboxError("predicate source is not valid expression syntax") from exc
    _validate(tree)
    code = compile(tree, "<quality-predicate>", "eval")
    globals_scope = {"__builtins__": _SAFE_BUILTINS}
    locals_scope = {"rows": tuple(dict(row) for row in rows)}
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(eval, code, globals_scope, locals_scope)  # noqa: S307
        try:
            result = future.result(timeout=timeout_seconds)
        except TimeoutError as exc:
            raise PredicateSandboxError("predicate execution timed out") from exc
    if not isinstance(result, bool):
        raise PredicateSandboxError("predicate must return a boolean")
    return result


__all__ = ("PredicateSandboxError", "evaluate_python_predicate")
