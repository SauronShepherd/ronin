"""Deterministic static analysis for generated PySpark programs."""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

Severity = Literal["info", "warning", "error"]
AutomationMode = Literal["AUTO_SAFE", "SHADOW_ONLY", "REVIEW", "ADVISORY"]


@dataclass(frozen=True, slots=True)
class AnalyzerSpec:
    analyzer_id: str
    version: str
    analyze: Callable[[str], tuple[Finding, ...]]

    def __post_init__(self) -> None:
        if not self.analyzer_id or self.analyzer_id != self.analyzer_id.strip():
            raise ValueError("analyzer id must be non-empty and trimmed")
        if not self.version or self.version != self.version.strip():
            raise ValueError("analyzer version must be non-empty and trimmed")


class AnalyzerRegistry:
    """Deterministic registry for provider-neutral migration analyzers."""

    def __init__(self) -> None:
        self._items: dict[str, AnalyzerSpec] = {}
        self._frozen = False

    def add(self, spec: AnalyzerSpec) -> None:
        if self._frozen:
            raise ValueError("analyzer registry is frozen")
        if spec.analyzer_id in self._items:
            raise ValueError(f"analyzer collision: {spec.analyzer_id}")
        self._items[spec.analyzer_id] = spec

    def freeze(self) -> None:
        self._frozen = True

    @property
    def items(self) -> tuple[AnalyzerSpec, ...]:
        return tuple(self._items[key] for key in sorted(self._items))

    def analyze(self, analyzer_id: str, source: str) -> tuple[Finding, ...]:
        try:
            spec = self._items[analyzer_id]
        except KeyError as exc:
            raise ValueError(f"unknown analyzer: {analyzer_id}") from exc
        return tuple(
            sorted(spec.analyze(source), key=lambda item: (item.line, item.column, item.rule_id))
        )


@dataclass(frozen=True, slots=True)
class Finding:
    rule_id: str
    severity: Severity
    confidence: float
    line: int
    column: int
    explanation: str
    recommendation: str
    automation: AutomationMode

    def to_payload(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "confidence": self.confidence,
            "line": self.line,
            "column": self.column,
            "explanation": self.explanation,
            "recommendation": self.recommendation,
            "automation": self.automation,
        }


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Attribute):
        owner = (
            _call_name(node.func.value)
            if isinstance(node.func.value, ast.Call)
            else (node.func.value.id if isinstance(node.func.value, ast.Name) else "")
        )
        return f"{owner}.{node.func.attr}" if owner else node.func.attr
    return node.func.id if isinstance(node.func, ast.Name) else ""


def analyze_pyspark(source: str) -> tuple[Finding, ...]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return (
            Finding(
                "PYTHON_SYNTAX",
                "error",
                1.0,
                exc.lineno or 1,
                exc.offset or 0,
                "generated program is not valid Python",
                "fix syntax before qualification",
                "REVIEW",
            ),
        )
    findings: list[Finding] = []
    cache_lines: list[int] = []
    unpersist_lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name.endswith(".collect") or name.endswith(".toPandas"):
            findings.append(
                Finding(
                    "DRIVER_MATERIALIZATION",
                    "warning",
                    0.99,
                    node.lineno,
                    node.col_offset,
                    f"{name} materializes distributed data on the driver",
                    "prefer distributed writes, aggregations, or bounded sampling",
                    "REVIEW",
                )
            )
        elif (
            name.endswith(".repartition")
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == 1
        ):
            findings.append(
                Finding(
                    "SINGLE_PARTITION",
                    "warning",
                    0.98,
                    node.lineno,
                    node.col_offset,
                    "repartition(1) forces a single output partition",
                    "remove it or justify the single-file contract",
                    "REVIEW",
                )
            )
        elif (
            name.endswith(".coalesce")
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == 1
        ):
            findings.append(
                Finding(
                    "SINGLE_PARTITION",
                    "warning",
                    0.98,
                    node.lineno,
                    node.col_offset,
                    "coalesce(1) can create a single-task bottleneck",
                    "avoid it unless a bounded output requires it",
                    "REVIEW",
                )
            )
        elif name.endswith(".cache") or name.endswith(".persist"):
            cache_lines.append(node.lineno)
        elif name.endswith(".unpersist"):
            unpersist_lines.append(node.lineno)
        elif name in {"udf", "pandas_udf", "F.udf", "functions.udf"} or name.endswith(".udf"):
            findings.append(
                Finding(
                    "PYTHON_UDF",
                    "warning",
                    0.95,
                    node.lineno,
                    node.col_offset,
                    "Python UDF may cross the JVM/Python boundary for every batch",
                    "prefer native Spark SQL expressions or a justified pandas UDF",
                    "REVIEW",
                )
            )
    if cache_lines and not unpersist_lines:
        findings.append(
            Finding(
                "CACHE_WITHOUT_UNPERSIST",
                "warning",
                0.9,
                cache_lines[0],
                0,
                "cache/persist is used without an unpersist in the program",
                "unpersist explicitly after the final dependent action",
                "REVIEW",
            )
        )
    return tuple(sorted(findings, key=lambda item: (item.line, item.rule_id)))


__all__ = ("AnalyzerRegistry", "AnalyzerSpec", "Finding", "analyze_pyspark")
