"""Executable built-in Data Quality evaluator for Ronin Public v1."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import TypeAlias

from studio_core import (
    DataContract,
    QualityResult,
    QualityRule,
    QualityRun,
    QualityRunId,
)

Row: TypeAlias = Mapping[str, object]


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
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be numeric") from exc


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
    assert max_nulls is not None
    observed = (("null_count", str(nulls)), ("row_count", str(len(rows))))
    if nulls <= max_nulls:
        return _passed(rule, observed)
    return _failed(rule, observed, f"null count {nulls} exceeds maximum {max_nulls}")


def _evaluate_unique(rule: QualityRule, rows: Sequence[Row]) -> QualityResult:
    values = _field_values(rule, rows)
    parameters = _parameters(rule)
    ignore_nulls = parameters.get("ignore_nulls", "true").casefold() == "true"
    normalized = [value for value in values if value is not None or not ignore_nulls]
    counts = Counter(repr(value) for value in normalized)
    duplicates = sum(count - 1 for count in counts.values() if count > 1)
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
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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
) -> QualityResult:
    """Evaluate one built-in rule; unsupported executable kinds report typed errors."""

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        if rule.kind == "null":
            return _evaluate_null(rule, rows)
        if rule.kind == "unique":
            return _evaluate_unique(rule, rows)
        if rule.kind == "range":
            return _evaluate_range(rule, rows)
        if rule.kind == "domain":
            return _evaluate_domain(rule, rows)
        if rule.kind == "row_count":
            return _evaluate_row_count(rule, rows)
        if rule.kind == "freshness":
            return _evaluate_freshness(rule, rows, now=current, contract=contract)
        if rule.kind == "referential":
            return _error(rule, "referential rules require a reference-dataset resolver")
        if rule.kind == "custom_sql":
            return _error(rule, "custom_sql execution is not enabled in the built-in evaluator")
        if rule.kind == "custom_python":
            return _error(rule, "custom_python execution is not enabled in the built-in evaluator")
        return _error(rule, f"unsupported quality rule kind: {rule.kind}")
    except (TypeError, ValueError) as exc:
        return _error(rule, str(exc))


def evaluate_contract(
    contract: DataContract,
    rows: Sequence[Row],
    *,
    run_id: QualityRunId,
    execution_ref: str | None = None,
    now: datetime | None = None,
) -> QualityRun:
    """Evaluate all contract rules deterministically into one immutable QualityRun."""

    results = tuple(
        evaluate_rule(rule, rows, contract=contract, now=now)
        for rule in contract.rules
    )
    return QualityRun(run_id, contract.asset, execution_ref, results)


def blocking_failures(contract: DataContract, run: QualityRun) -> tuple[QualityResult, ...]:
    """Return failed/error results whose contract rule is marked blocking."""

    blocking = {rule.id for rule in contract.rules if rule.blocking}
    return tuple(
        result
        for result in run.results
        if result.rule_id in blocking and result.status in {"failed", "error"}
    )


__all__ = ("Row", "blocking_failures", "evaluate_contract", "evaluate_rule")
