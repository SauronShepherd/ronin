"""Bounded expression evaluator for custom quality predicates."""

from __future__ import annotations

import ast
import math
import multiprocessing
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess


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


def _predicate_worker(
    send_connection: Connection,
    expression: str,
    rows: tuple[dict[str, object], ...],
) -> None:
    try:
        tree = ast.parse(expression, mode="eval")
        _validate(tree)
        code = compile(tree, "<quality-predicate>", "eval")
        result = eval(  # noqa: S307 - the AST and builtin set are restricted above
            code,
            {"__builtins__": _SAFE_BUILTINS, "rows": rows},
            {},
        )
        if not isinstance(result, bool):
            send_connection.send((False, "predicate must return a boolean"))
        else:
            send_connection.send((True, result))
    except BaseException as exc:
        with suppress(BrokenPipeError, EOFError, OSError):
            send_connection.send((False, f"predicate execution failed ({type(exc).__name__})"))
    finally:
        send_connection.close()


def _stop_worker(process: BaseProcess) -> None:
    process.join(timeout=0.05)
    if process.is_alive():
        process.terminate()
        process.join(timeout=0.2)
    if process.is_alive():
        process.kill()
        process.join()
    else:
        process.join(timeout=0)


def evaluate_python_predicate(
    expression: str,
    rows: Sequence[Mapping[str, object]],
    *,
    timeout_seconds: float = 10.0,
    max_source_chars: int = 4_000,
    max_rows: int = 10_000,
) -> bool:
    if not expression or len(expression) > max_source_chars:
        raise PredicateSandboxError("predicate source exceeds configured limit")
    if (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
        or timeout_seconds > 10
    ):
        raise PredicateSandboxError("predicate timeout is outside configured bounds")
    if len(rows) > max_rows:
        raise PredicateSandboxError("predicate input exceeds configured row limit")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise PredicateSandboxError("predicate source is not valid expression syntax") from exc
    _validate(tree)
    try:
        compile(tree, "<quality-predicate>", "eval")
    except (TypeError, ValueError) as exc:
        raise PredicateSandboxError("predicate source could not be compiled") from exc

    safe_rows = tuple(dict(row) for row in rows)
    context = multiprocessing.get_context("spawn")
    receive_connection, send_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=_predicate_worker,
        args=(send_connection, expression, safe_rows),
        name="quality-predicate",
        daemon=True,
    )
    deadline = time.monotonic() + timeout_seconds
    try:
        process.start()
    except Exception as exc:
        receive_connection.close()
        send_connection.close()
        raise PredicateSandboxError("predicate worker could not start") from exc
    send_connection.close()
    try:
        remaining = max(0.0, deadline - time.monotonic())
        if receive_connection.poll(remaining):
            try:
                succeeded, result = receive_connection.recv()
            except (EOFError, OSError) as exc:
                raise PredicateSandboxError("predicate worker exited without a result") from exc
            _stop_worker(process)
            if not succeeded:
                raise PredicateSandboxError(str(result))
            return bool(result)
        if process.exitcode is not None:
            raise PredicateSandboxError("predicate worker exited without a result")
        raise PredicateSandboxError("predicate execution timed out")
    finally:
        receive_connection.close()
        _stop_worker(process)


__all__ = ("PredicateSandboxError", "evaluate_python_predicate")
