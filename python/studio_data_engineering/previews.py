"""Small deterministic preview engine for Data Enginerring Studio.

This is intentionally a bounded fixture engine, not a general Python evaluator
and not a replacement for Spark. It exists to make authoring feedback fast.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass

from studio_core.ir import Edge, Node, Pipeline
from studio_core.operators import builtin_operator_catalog, operator_parameter_value

from .compiler import compile_pipeline


class PreviewError(ValueError):
    """A preview cannot be evaluated safely or deterministically."""


@dataclass(frozen=True, slots=True)
class PreviewResult:
    runtime: str
    rows_by_node: Mapping[str, tuple[Mapping[str, object], ...]]
    metrics: Mapping[str, Mapping[str, int]]
    diagnostics: tuple[str, ...] = ()


def preview_pipeline(
    data: Mapping[str, object],
    *,
    fixtures: Mapping[str, list[Mapping[str, object]]],
    row_limit: int = 100,
) -> PreviewResult:
    if row_limit < 1 or row_limit > 10_000:
        raise PreviewError("row_limit must be between 1 and 10000")
    report = compile_pipeline(
        data, runtime="local-preview", catalog=builtin_operator_catalog()
    )
    if not report.portable:
        raise PreviewError("pipeline is not valid for local preview")
    try:
        pipeline = Pipeline.from_data(data)
    except (TypeError, ValueError) as exc:
        raise PreviewError(str(exc)) from exc

    by_id = {node.id: node for node in pipeline.nodes}
    incoming: dict[object, list[Edge]] = {node.id: [] for node in pipeline.nodes}
    outgoing: dict[object, list[Edge]] = {node.id: [] for node in pipeline.nodes}
    for edge in pipeline.edges:
        incoming[edge.target].append(edge)
        outgoing[edge.source].append(edge)
    order = _topological_order(pipeline)
    values: dict[object, tuple[Mapping[str, object], ...]] = {}
    metrics: dict[str, Mapping[str, int]] = {}

    for node_id in order:
        node = by_id[node_id]
        operator = node.operator.name
        rows = _input_rows(node, incoming[node_id], values, fixtures)
        result = _apply(node, operator, rows, row_limit)
        values[node_id] = result
        metrics[node.instance_key] = {
            "input_rows": len(rows),
            "output_rows": len(result),
        }

    return PreviewResult(
        runtime="local-preview",
        rows_by_node={
            by_id[node_id].instance_key: rows for node_id, rows in values.items()
        },
        metrics=metrics,
    )


def _input_rows(
    node: Node,
    edges: list[Edge],
    values: Mapping[object, tuple[Mapping[str, object], ...]],
    fixtures: Mapping[str, list[Mapping[str, object]]],
) -> tuple[Mapping[str, object], ...]:
    if node.operator.name == "source.fixture":
        fixture = operator_parameter_value(node, "fixture")
        if not isinstance(fixture, str) or fixture not in fixtures:
            raise PreviewError(f"fixture is not available: {fixture!r}")
        return tuple(fixtures[fixture])
    if not edges:
        return ()
    if node.operator.name == "transform.join":
        left = next(edge for edge in edges if edge.target_port == "left")
        right = next(edge for edge in edges if edge.target_port == "right")
        return tuple(
            {**dict(values[left.source][0]), **dict(values[right.source][0])}
            if values[left.source] and values[right.source]
            else {}
        for _ in [0])
    return values[edges[0].source]


def _apply(
    node: Node,
    operator: str,
    rows: tuple[Mapping[str, object], ...],
    row_limit: int,
) -> tuple[Mapping[str, object], ...]:
    if operator == "source.fixture":
        return rows[:row_limit]
    if operator == "transform.filter":
        expression = operator_parameter_value(node, "expression")
        if not isinstance(expression, str):
            raise PreviewError("filter expression must be a string")
        return tuple(row for row in rows if _evaluate(expression, row))[:row_limit]
    if operator == "transform.select":
        columns = operator_parameter_value(node, "columns")
        if not isinstance(columns, list) or not all(isinstance(c, str) for c in columns):
            raise PreviewError("select columns must be an array of strings")
        return tuple({column: row.get(column) for column in columns} for row in rows)[:row_limit]
    if operator == "transform.derive":
        name = operator_parameter_value(node, "name")
        expression = operator_parameter_value(node, "expression")
        if not isinstance(name, str) or not isinstance(expression, str):
            raise PreviewError("derive name and expression must be strings")
        return tuple({**dict(row), name: _evaluate(expression, row)} for row in rows)[:row_limit]
    return rows[:row_limit]


def _topological_order(pipeline: Pipeline) -> list[object]:
    incoming = {node.id: 0 for node in pipeline.nodes}
    outgoing: dict[object, list[object]] = {node.id: [] for node in pipeline.nodes}
    for edge in pipeline.edges:
        incoming[edge.target] += 1
        outgoing[edge.source].append(edge.target)
    queue = sorted(node_id for node_id, count in incoming.items() if count == 0)
    result: list[object] = []
    while queue:
        current = queue.pop(0)
        result.append(current)
        for target in sorted(outgoing[current]):
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
                queue.sort()
    return result


def _evaluate(expression: str, row: Mapping[str, object]) -> object:
    try:
        tree = ast.parse(expression, mode="eval")
        return _eval_node(tree.body, row)
    except (SyntaxError, TypeError, ValueError, KeyError, ZeroDivisionError) as exc:
        raise PreviewError(f"unsafe or invalid expression: {expression}") from exc


def _eval_node(node: ast.AST, row: Mapping[str, object]) -> object:
    if isinstance(node, ast.Name):
        if node.id not in row:
            raise KeyError(node.id)
        return row[node.id]
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool)):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        left, right = _eval_node(node.left, row), _eval_node(node.right, row)
        return {ast.Add: lambda: left + right, ast.Sub: lambda: left - right,
                ast.Mult: lambda: left * right, ast.Div: lambda: left / right}[type(node.op)]()
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        left, right = _eval_node(node.left, row), _eval_node(node.comparators[0], row)
        operator = node.ops[0]
        if isinstance(operator, ast.Eq):
            return left == right
        if isinstance(operator, ast.NotEq):
            return left != right
        if isinstance(operator, ast.Gt):
            return left > right
        if isinstance(operator, ast.GtE):
            return left >= right
        if isinstance(operator, ast.Lt):
            return left < right
        if isinstance(operator, ast.LtE):
            return left <= right
    if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
        values = [_eval_node(value, row) for value in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval_node(node.operand, row)
    raise ValueError("expression node is not allowed")


__all__ = ("PreviewError", "PreviewResult", "preview_pipeline")
