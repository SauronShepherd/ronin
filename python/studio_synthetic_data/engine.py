"""Dependency-free synthetic data engine for local development.

The engine deliberately separates authored intent (schema, relationships and seed)
from execution. It produces deterministic, inspectable output and never claims
privacy merely because values are synthetic.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import re
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol


class GovernanceState(StrEnum):
    DRAFT = "draft"
    GENERATED = "generated"
    VALIDATED = "validated"
    APPROVED = "approved"
    PUBLISHED = "published"


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    name: str
    kind: str = "string"
    nullable: bool = True
    null_rate: float = 0.0
    values: tuple[str, ...] = ()
    minimum: int = 0
    maximum: int = 100

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.name):
            raise ValueError(f"invalid column name: {self.name}")
        if self.kind not in {"string", "integer", "number", "boolean", "date", "email", "uuid"}:
            raise ValueError(f"unsupported column kind: {self.kind}")
        if not 0 <= self.null_rate <= 1:
            raise ValueError("null_rate must be between 0 and 1")
        if not self.nullable and self.null_rate:
            raise ValueError("non-nullable columns cannot have a null rate")


@dataclass(frozen=True, slots=True)
class ForeignKey:
    child_table: str
    child_column: str
    parent_table: str
    parent_column: str


@dataclass(frozen=True, slots=True)
class TableSpec:
    name: str
    columns: tuple[ColumnSpec, ...]
    primary_key: str | None = None
    rows: int = 100

    def __post_init__(self) -> None:
        names = [column.name for column in self.columns]
        if not self.name or len(set(names)) != len(names):
            raise ValueError("table and column names must be non-empty and unique")
        if self.primary_key is not None and self.primary_key not in names:
            raise ValueError(f"primary key is not a column: {self.primary_key}")
        if self.rows < 0:
            raise ValueError("rows must be non-negative")


@dataclass(frozen=True, slots=True)
class GenerationPlan:
    tables: tuple[TableSpec, ...]
    relationships: tuple[ForeignKey, ...] = ()
    seed: int = 0

    def __post_init__(self) -> None:
        names = {table.name for table in self.tables}
        if len(names) != len(self.tables):
            raise ValueError("table names must be unique")
        for relation in self.relationships:
            if relation.parent_table not in names or relation.child_table not in names:
                raise ValueError("relationship references an unknown table")


@dataclass(frozen=True, slots=True)
class SyntheticTable:
    name: str
    rows: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class GenerationResult:
    tables: tuple[SyntheticTable, ...]
    plan_fingerprint: str
    warnings: tuple[str, ...] = ()
    state: GovernanceState = GovernanceState.GENERATED


@dataclass(frozen=True, slots=True)
class ValidationReport:
    passed: bool
    checks: tuple[str, ...]
    errors: tuple[str, ...] = ()
    evidence_id: str = ""


@dataclass(frozen=True, slots=True)
class PrivacyAssessment:
    status: str
    generated_rows: int
    exact_row_matches: int
    warnings: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {"status": self.status, "generated_rows": self.generated_rows, "exact_row_matches": self.exact_row_matches, "warnings": list(self.warnings)}


@dataclass(frozen=True, slots=True)
class ColumnProfile:
    name: str
    row_count: int
    null_count: int
    distinct_count: int
    frequencies: tuple[tuple[str, int], ...] = ()

    @property
    def null_rate(self) -> float:
        return self.null_count / self.row_count if self.row_count else 0.0


@dataclass(frozen=True, slots=True)
class TableProfile:
    name: str
    row_count: int
    columns: tuple[ColumnProfile, ...]


class Exporter(Protocol):
    format_id: str

    def export(self, table: SyntheticTable) -> str: ...


class ExporterRegistry:
    """Provider registry for built-in and third-party exporters."""

    def __init__(self, exporters: tuple[Exporter, ...] = ()) -> None:
        self._exporters: dict[str, Exporter] = {}
        for exporter in exporters:
            self.register(exporter)

    def register(self, exporter: Exporter) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", exporter.format_id):
            raise ValueError(f"invalid exporter id: {exporter.format_id}")
        if exporter.format_id in self._exporters:
            raise ValueError(f"exporter already registered: {exporter.format_id}")
        self._exporters[exporter.format_id] = exporter

    def export(self, format_id: str, table: SyntheticTable) -> str:
        try:
            exporter = self._exporters[format_id]
        except KeyError as exc:
            raise ValueError(f"unknown exporter: {format_id}") from exc
        return exporter.export(table)

    @property
    def formats(self) -> tuple[str, ...]:
        return tuple(sorted(self._exporters))


class CsvExporter:
    format_id = "csv"

    def export(self, table: SyntheticTable) -> str:
        columns = list(table.rows[0]) if table.rows else []
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(table.rows)
        return stream.getvalue()


class JsonlExporter:
    format_id = "jsonl"

    def export(self, table: SyntheticTable) -> str:
        return "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in table.rows)


def _value(column: ColumnSpec, index: int, rng: random.Random) -> object:
    if column.nullable and rng.random() < column.null_rate:
        return None
    if column.values:
        return rng.choice(column.values)
    if column.kind == "integer":
        return rng.randint(column.minimum, column.maximum)
    if column.kind == "number":
        return round(rng.uniform(column.minimum, column.maximum), 2)
    if column.kind == "boolean":
        return bool(rng.getrandbits(1))
    if column.kind == "email":
        return f"user{index}@example.test"
    if column.kind == "uuid":
        return f"{rng.getrandbits(128):032x}"
    if column.kind == "date":
        return f"2024-{(index % 12) + 1:02d}-{(index % 28) + 1:02d}"
    return f"{column.name}_{index + 1}"


def profile(sample: dict[str, tuple[dict[str, object], ...]]) -> tuple[TableProfile, ...]:
    """Produce deterministic, bounded evidence from an optional source sample."""
    profiles: list[TableProfile] = []
    for table_name in sorted(sample):
        rows = sample[table_name]
        columns = sorted({key for row in rows for key in row})
        column_profiles: list[ColumnProfile] = []
        for column in columns:
            values = [row.get(column) for row in rows]
            non_null = [value for value in values if value is not None]
            counts: dict[str, int] = {}
            for value in non_null:
                key = str(value)
                counts[key] = counts.get(key, 0) + 1
            top_values = tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:20])
            column_profiles.append(
                ColumnProfile(
                    column, len(rows), len(values) - len(non_null), len(counts), top_values
                )
            )
        profiles.append(TableProfile(table_name, len(rows), tuple(column_profiles)))
    return tuple(profiles)


def generate(
    plan: GenerationPlan, sample: dict[str, tuple[dict[str, object], ...]] | None = None
) -> GenerationResult:
    """Generate parent tables first, then resolve declared foreign keys."""
    rng = random.Random(plan.seed)  # noqa: S311 - reproducibility, never cryptographic
    generated: dict[str, list[dict[str, object]]] = {}
    warnings: list[str] = []
    for table in plan.tables:
        source_rows = (sample or {}).get(table.name, ())
        columns = tuple(
            replace(
                column,
                values=tuple(
                    dict.fromkeys(
                        str(row[column.name])
                        for row in source_rows
                        if row.get(column.name) is not None
                    )
                )
                if not column.values and column.kind == "string"
                else column.values,
            )
            for column in table.columns
        )
        generated[table.name] = [
            {column.name: _value(column, row_index, rng) for column in columns}
            for row_index in range(table.rows)
        ]
        if table.primary_key:
            key = next(column for column in columns if column.name == table.primary_key)
            if key.kind in {"integer", "uuid"}:
                for row_index, row in enumerate(generated[table.name], start=1):
                    row[table.primary_key] = (
                        row_index if key.kind == "integer" else f"{plan.seed:08x}-{row_index:024x}"
                    )
        if sample and table.name in sample:
            warnings.append(f"sample provided for {table.name}; schema-aware generation is active")
    for relation in plan.relationships:
        parents = generated[relation.parent_table]
        if not parents:
            warnings.append(f"relationship skipped because {relation.parent_table} has no rows")
            continue
        values = [row[relation.parent_column] for row in parents]
        for row in generated[relation.child_table]:
            row[relation.child_column] = rng.choice(values)
    payload = json.dumps(
        {"tables": [table.name for table in plan.tables], "seed": plan.seed}, sort_keys=True
    )
    fingerprint = "synthetic-plan-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return GenerationResult(
        tuple(SyntheticTable(name, tuple(rows)) for name, rows in generated.items()),
        fingerprint,
        tuple(warnings),
    )


def validate(plan: GenerationPlan, result: GenerationResult) -> ValidationReport:
    errors: list[str] = []
    checks = [
        "schema",
        "row_count",
        "nullability",
        "primary_key_uniqueness",
        "foreign_key_integrity",
        "privacy_disclaimer",
    ]
    by_name = {table.name: table for table in result.tables}
    for spec in plan.tables:
        table = by_name.get(spec.name)
        if table is None:
            errors.append(f"missing table: {spec.name}")
            continue
        expected = {column.name for column in spec.columns}
        if any(set(row) != expected for row in table.rows):
            errors.append(f"schema mismatch: {spec.name}")
        if len(table.rows) != spec.rows:
            errors.append(f"row count mismatch: {spec.name}")
        for column in spec.columns:
            if not column.nullable and any(row.get(column.name) is None for row in table.rows):
                errors.append(f"nullability violation: {spec.name}.{column.name}")
        if spec.primary_key:
            keys = [row[spec.primary_key] for row in table.rows]
            if len(keys) != len(set(keys)):
                errors.append(f"duplicate primary key: {spec.name}.{spec.primary_key}")
    for relation in plan.relationships:
        parent = {row[relation.parent_column] for row in by_name[relation.parent_table].rows}
        if any(
            row[relation.child_column] not in parent for row in by_name[relation.child_table].rows
        ):
            errors.append(f"broken foreign key: {relation.child_table}.{relation.child_column}")
    evidence = (
        "validation-"
        + hashlib.sha256(
            json.dumps({"plan": result.plan_fingerprint, "errors": errors}, sort_keys=True).encode()
        ).hexdigest()[:16]
    )
    return ValidationReport(not errors, tuple(checks), tuple(errors), evidence)


def assess_privacy(result: GenerationResult, source_sample: dict[str, tuple[dict[str, object], ...]] | None = None) -> PrivacyAssessment:
    """Assess exact row reuse; this is evidence, not an anonymity guarantee."""
    generated = [row for table in result.tables for row in table.rows]
    if source_sample is None:
        return PrivacyAssessment("not_assessed", len(generated), 0, ("no source sample supplied; synthetic output is not proven anonymous",))
    source_rows = {json.dumps(row, sort_keys=True, default=str, separators=(",", ":")) for rows in source_sample.values() for row in rows}
    matches = sum(json.dumps(row, sort_keys=True, default=str, separators=(",", ":")) in source_rows for row in generated)
    return PrivacyAssessment("review_required" if matches else "no_exact_matches_observed", len(generated), matches, ("exact generated rows match source sample",) if matches else ())


__all__ = [
    "ColumnSpec",
    "ColumnProfile",
    "CsvExporter",
    "Exporter",
    "ExporterRegistry",
    "ForeignKey",
    "GenerationPlan",
    "GenerationResult",
    "GovernanceState",
    "JsonlExporter",
    "SyntheticTable",
    "TableSpec",
    "TableProfile",
    "ValidationReport",
    "PrivacyAssessment",
    "generate",
    "profile",
    "validate",
    "assess_privacy",
]
