"""Executable built-in Data Quality evaluator for Ronin Public v1."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import TypeAlias, cast

from studio_core import (
    DataContract,
    QualityResult,
    QualityRule,
    QualityRun,
    QualityRunId,
)

from .sandbox import evaluate_python_predicate

Row: TypeAlias = Mapping[str, object]


@dataclass(frozen=True, slots=True)
class QualityEvaluationBudget:
    """Hard input bounds and a cooperative wall-time budget for evaluation."""

    max_rows: int = 10_000
    max_row_bytes: int = 64 * 1024
    max_total_bytes: int = 4 * 1024 * 1024
    max_cells: int = 250_000
    max_rules: int = 100
    max_wall_time_seconds: float = 30.0

    def __post_init__(self) -> None:
        for name in ("max_rows", "max_row_bytes", "max_total_bytes", "max_cells", "max_rules"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"quality budget {name} must be a positive integer")
        if (
            not isinstance(self.max_wall_time_seconds, (int, float))
            or isinstance(self.max_wall_time_seconds, bool)
            or not math.isfinite(self.max_wall_time_seconds)
            or self.max_wall_time_seconds <= 0
            or self.max_wall_time_seconds > 300
        ):
            raise ValueError("quality budget max_wall_time_seconds must be between 0 and 300")

    def validate_rows(self, rows: Sequence[Row]) -> None:
        if len(rows) > self.max_rows:
            raise ValueError(f"quality row budget exceeded: maximum is {self.max_rows}")
        total_bytes = 0
        total_cells = 0
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping) or not all(isinstance(key, str) for key in row):
                raise ValueError("quality rows must be objects with string keys")
            total_cells += len(row)
            if total_cells > self.max_cells:
                raise ValueError(f"quality cell budget exceeded: maximum is {self.max_cells}")
            try:
                encoded = json.dumps(
                    dict(row),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=True,
                    default=str,
                ).encode("utf-8")
            except (RecursionError, TypeError, ValueError, UnicodeEncodeError) as exc:
                raise ValueError(f"quality row {index} is not valid bounded JSON data") from exc
            if len(encoded) > self.max_row_bytes:
                raise ValueError(
                    f"quality row byte budget exceeded at row {index}: maximum is "
                    f"{self.max_row_bytes}"
                )
            total_bytes += len(encoded)
            if total_bytes > self.max_total_bytes:
                raise ValueError(
                    f"quality total input byte budget exceeded: maximum is {self.max_total_bytes}"
                )

    def validate(self, contract: DataContract, rows: Sequence[Row]) -> None:
        self.validate_rows(rows)
        if len(contract.rules) > self.max_rules:
            raise ValueError(f"quality rule budget exceeded: maximum is {self.max_rules}")


DEFAULT_QUALITY_EVALUATION_BUDGET = QualityEvaluationBudget()


def _parameters(rule: QualityRule) -> dict[str, str]:
    return dict(rule.parameters)


def _field_values(rule: QualityRule, rows: Sequence[Row]) -> tuple[object, ...]:
    if rule.field is None:
        raise ValueError(f"quality rule {rule.id} requires field")
    missing = sum(1 for row in rows if rule.field not in row)
    if missing:
        raise ValueError(f"field {rule.field!r} is missing from {missing} row(s)")
    return tuple(row[rule.field] for row in rows)


def _decimal(value: object, *, name: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name} must be numeric")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not parsed.is_finite():
        raise ValueError(f"{name} must be finite")
    return parsed


def _unique_key(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("unique values must not contain non-finite numbers")
    if isinstance(value, Decimal) and not value.is_finite():
        raise ValueError("unique values must not contain non-finite numbers")
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    if isinstance(value, Mapping):
        return (
            "mapping",
            frozenset((_unique_key(key), _unique_key(child)) for key, child in value.items()),
        )
    if isinstance(value, list):
        return ("list", tuple(_unique_key(child) for child in value))
    if isinstance(value, tuple):
        return ("tuple", tuple(_unique_key(child) for child in value))
    if isinstance(value, set):
        return ("set", frozenset(_unique_key(child) for child in value))
    if isinstance(value, frozenset):
        return ("set", frozenset(_unique_key(child) for child in value))
    try:
        hash(value)
    except TypeError as exc:
        raise ValueError("unique rule encountered an unsupported unhashable value") from exc
    return value


def _parse_int(parameters: dict[str, str], key: str, default: int | None = None) -> int | None:
    value = parameters.get(key)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"quality parameter {key} must be an integer") from exc
    if parsed < 0:
        raise ValueError(f"quality parameter {key} must be non-negative")
    return parsed


def _passed(rule: QualityRule, observed: tuple[tuple[str, str], ...]) -> QualityResult:
    return QualityResult(rule.id, "passed", observed)


def _failed(
    rule: QualityRule,
    observed: tuple[tuple[str, str], ...],
    message: str,
) -> QualityResult:
    return QualityResult(rule.id, "failed", observed, message)


def _error(rule: QualityRule, message: str) -> QualityResult:
    return QualityResult(rule.id, "error", (), message)


def _evaluate_null(rule: QualityRule, rows: Sequence[Row]) -> QualityResult:
    values = _field_values(rule, rows)
    nulls = sum(value is None for value in values)
    parameters = _parameters(rule)
    max_nulls = _parse_int(parameters, "max_nulls", 0)
    if max_nulls is None:
        raise ValueError("quality parameter max_nulls must be an integer")
    observed = (("null_count", str(nulls)), ("row_count", str(len(rows))))
    if nulls <= max_nulls:
        return _passed(rule, observed)
    return _failed(rule, observed, f"null count {nulls} exceeds maximum {max_nulls}")


def _evaluate_unique(rule: QualityRule, rows: Sequence[Row]) -> QualityResult:
    values = _field_values(rule, rows)
    parameters = _parameters(rule)
    ignore_nulls = parameters.get("ignore_nulls", "true").casefold() == "true"
    normalized = [value for value in values if value is not None or not ignore_nulls]
    seen: set[object] = set()
    duplicates = 0
    for value in normalized:
        key = _unique_key(value)
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)
    observed = (("duplicate_count", str(duplicates)), ("row_count", str(len(rows))))
    if duplicates == 0:
        return _passed(rule, observed)
    return _failed(rule, observed, f"found {duplicates} duplicate value(s)")


def _evaluate_range(rule: QualityRule, rows: Sequence[Row]) -> QualityResult:
    values = _field_values(rule, rows)
    parameters = _parameters(rule)
    minimum = parameters.get("min")
    maximum = parameters.get("max")
    if minimum is None and maximum is None:
        raise ValueError("range rule requires min and/or max parameter")
    minimum_value = None if minimum is None else _decimal(minimum, name="range min")
    maximum_value = None if maximum is None else _decimal(maximum, name="range max")
    if minimum_value is not None and maximum_value is not None and minimum_value > maximum_value:
        raise ValueError("range min must not exceed range max")
    violations = 0
    numeric_values: list[Decimal] = []
    for value in values:
        if value is None:
            continue
        numeric = _decimal(value, name=f"field {rule.field}")
        numeric_values.append(numeric)
        if minimum_value is not None and numeric < minimum_value:
            violations += 1
        if maximum_value is not None and numeric > maximum_value:
            violations += 1
    observed_items = [("violation_count", str(violations))]
    if numeric_values:
        observed_items.extend(
            (("observed_min", str(min(numeric_values))), ("observed_max", str(max(numeric_values))))
        )
    observed = tuple(observed_items)
    if violations == 0:
        return _passed(rule, observed)
    return _failed(rule, observed, f"found {violations} out-of-range value(s)")


def _evaluate_domain(rule: QualityRule, rows: Sequence[Row]) -> QualityResult:
    values = _field_values(rule, rows)
    allowed_raw = _parameters(rule).get("allowed")
    if allowed_raw is None:
        raise ValueError("domain rule requires allowed parameter")
    allowed = {item.strip() for item in allowed_raw.split(",") if item.strip()}
    if not allowed:
        raise ValueError("domain allowed parameter must contain at least one value")
    invalid = sum(value is not None and str(value) not in allowed for value in values)
    observed = (("invalid_count", str(invalid)), ("allowed_count", str(len(allowed))))
    if invalid == 0:
        return _passed(rule, observed)
    return _failed(rule, observed, f"found {invalid} value(s) outside the allowed domain")


def _evaluate_row_count(rule: QualityRule, rows: Sequence[Row]) -> QualityResult:
    parameters = _parameters(rule)
    minimum = _parse_int(parameters, "min")
    maximum = _parse_int(parameters, "max")
    if minimum is None and maximum is None:
        raise ValueError("row_count rule requires min and/or max parameter")
    count = len(rows)
    observed = (("row_count", str(count)),)
    if minimum is not None and count < minimum:
        return _failed(rule, observed, f"row count {count} is below minimum {minimum}")
    if maximum is not None and count > maximum:
        return _failed(rule, observed, f"row count {count} exceeds maximum {maximum}")
    return _passed(rule, observed)


def _parse_timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError as exc:
            raise ValueError("freshness field must contain ISO-8601 timestamps") from exc
    else:
        raise ValueError("freshness field must contain datetime or ISO-8601 string values")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _evaluate_freshness(
    rule: QualityRule,
    rows: Sequence[Row],
    *,
    now: datetime,
    contract: DataContract,
) -> QualityResult:
    values = _field_values(rule, rows)
    non_null = [_parse_timestamp(value) for value in values if value is not None]
    if not non_null:
        return _failed(rule, (("observed_rows", "0"),), "freshness field has no timestamps")
    parameters = _parameters(rule)
    max_age = _parse_int(parameters, "max_age_seconds", contract.freshness_seconds)
    if max_age is None:
        raise ValueError("freshness rule requires max_age_seconds or contract freshness_seconds")
    latest = max(non_null)
    age_seconds = max(0, int((now - latest).total_seconds()))
    observed = (("age_seconds", str(age_seconds)), ("latest", latest.isoformat()))
    if age_seconds <= max_age:
        return _passed(rule, observed)
    return _failed(rule, observed, f"freshness age {age_seconds}s exceeds maximum {max_age}s")


def evaluate_rule(
    rule: QualityRule,
    rows: Sequence[Row],
    *,
    contract: DataContract,
    now: datetime | None = None,
    reference_values: Callable[[QualityRule], Sequence[object]] | None = None,
    custom_sql: Callable[[QualityRule, Sequence[Row]], bool] | None = None,
    custom_python: Callable[[QualityRule, Sequence[Row]], bool] | None = None,
    budget: QualityEvaluationBudget = DEFAULT_QUALITY_EVALUATION_BUDGET,
    deadline: float | None = None,
    _inputs_validated: bool = False,
) -> QualityResult:
    """Evaluate one built-in rule; unsupported executable kinds report typed errors."""

    current = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        if not _inputs_validated:
            budget.validate_rows(rows)
        if deadline is not None and time.monotonic() >= deadline:
            raise ValueError("quality evaluation exceeded wall-time budget")
        if rule.kind == "null":
            result = _evaluate_null(rule, rows)
        elif rule.kind == "unique":
            result = _evaluate_unique(rule, rows)
        elif rule.kind == "range":
            result = _evaluate_range(rule, rows)
        elif rule.kind == "domain":
            result = _evaluate_domain(rule, rows)
        elif rule.kind == "row_count":
            result = _evaluate_row_count(rule, rows)
        elif rule.kind == "freshness":
            result = _evaluate_freshness(rule, rows, now=current, contract=contract)
        elif rule.kind == "referential":
            if reference_values is None:
                return _error(rule, "referential rules require a reference-dataset resolver")
            values = _field_values(rule, rows)
            references = set(reference_values(rule))
            violations = sum(value is not None and value not in references for value in values)
            observed: tuple[tuple[str, str], ...] = (
                ("violation_count", str(violations)),
                ("reference_count", str(len(references))),
            )
            if violations == 0:
                result = _passed(rule, observed)
            else:
                result = _failed(
                    rule, observed, f"found {violations} value(s) missing from reference data"
                )
        elif rule.kind == "custom_sql":
            if custom_sql is None:
                return _error(rule, "custom_sql execution is not enabled in the built-in evaluator")
            passed = custom_sql(rule, rows)
            custom_observed: tuple[tuple[str, str], ...] = (
                ("predicate_passed", str(bool(passed)).lower()),
            )
            result = (
                _passed(rule, custom_observed)
                if passed
                else _failed(rule, custom_observed, "custom SQL predicate failed")
            )
        elif rule.kind == "custom_python":
            expression = _parameters(rule).get("expression")
            if custom_python is None and expression is None:
                return _error(
                    rule, "custom_python execution is not enabled in the built-in evaluator"
                )
            if custom_python is None:
                remaining = 10.0 if deadline is None else min(10.0, deadline - time.monotonic())
                if remaining <= 0:
                    raise ValueError("quality evaluation exceeded wall-time budget")
                passed = evaluate_python_predicate(
                    cast(str, expression), rows, timeout_seconds=remaining, max_rows=budget.max_rows
                )
            else:
                passed = custom_python(rule, rows)
            python_observed: tuple[tuple[str, str], ...] = (
                ("predicate_passed", str(bool(passed)).lower()),
            )
            result = (
                _passed(rule, python_observed)
                if passed
                else _failed(rule, python_observed, "custom Python predicate failed")
            )
        else:
            return _error(rule, f"unsupported quality rule kind: {rule.kind}")
        if deadline is not None and time.monotonic() >= deadline:
            return _error(rule, "quality evaluation exceeded wall-time budget")
        return result
    except (TypeError, ValueError) as exc:
        return _error(rule, str(exc))


def evaluate_contract(
    contract: DataContract,
    rows: Sequence[Row],
    *,
    run_id: QualityRunId,
    execution_ref: str | None = None,
    now: datetime | None = None,
    reference_values: Callable[[QualityRule], Sequence[object]] | None = None,
    custom_sql: Callable[[QualityRule, Sequence[Row]], bool] | None = None,
    custom_python: Callable[[QualityRule, Sequence[Row]], bool] | None = None,
    budget: QualityEvaluationBudget = DEFAULT_QUALITY_EVALUATION_BUDGET,
) -> QualityRun:
    """Evaluate all contract rules deterministically into one immutable QualityRun."""

    budget.validate(contract, rows)
    deadline = time.monotonic() + budget.max_wall_time_seconds
    results_list: list[QualityResult] = []
    for rule in contract.rules:
        results_list.append(
            evaluate_rule(
                rule,
                rows,
                contract=contract,
                now=now,
                reference_values=reference_values,
                custom_sql=custom_sql,
                custom_python=custom_python,
                budget=budget,
                deadline=deadline,
                _inputs_validated=True,
            )
        )
    results = tuple(results_list)
    return QualityRun(run_id, contract.asset, execution_ref, results)


def blocking_failures(contract: DataContract, run: QualityRun) -> tuple[QualityResult, ...]:
    """Return failed/error results whose contract rule is marked blocking."""

    blocking = {rule.id for rule in contract.rules if rule.blocking}
    return tuple(
        result
        for result in run.results
        if result.rule_id in blocking and result.status in {"failed", "error"}
    )


__all__ = (
    "DEFAULT_QUALITY_EVALUATION_BUDGET",
    "QualityEvaluationBudget",
    "Row",
    "blocking_failures",
    "evaluate_contract",
    "evaluate_rule",
)
