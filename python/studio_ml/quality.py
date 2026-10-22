"""Tabular profiling and declarative quality gates for Machine Learning Studio."""

from __future__ import annotations

# ruff: noqa: E501
import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Any, cast

from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.canonical_json import encode as encode_canonical_json

from .catalog import validate_catalog_version
from .domain import Lab


@dataclass(frozen=True, slots=True)
class QualityExpectation:
    id: str
    column: str
    rule: str
    severity: str = "failure"
    value: int | float | None = None

    def __post_init__(self) -> None:
        for item, name in ((self.id, "expectation id"), (self.column, "expectation column")):
            if not isinstance(item, str) or not item or item != item.strip() or len(item) > 256:
                raise ValueError(f"{name} must be trimmed text of at most 256 characters")
        if not isinstance(self.rule, str) or self.rule not in {
            "not_null",
            "numeric",
            "min",
            "max",
            "min_distinct",
        }:
            raise ValueError("unsupported quality expectation rule")
        if not isinstance(self.severity, str) or self.severity not in {"warning", "failure"}:
            raise ValueError("quality expectation severity must be warning or failure")
        if self.rule in {"min", "max"}:
            if (
                not isinstance(self.value, (int, float))
                or isinstance(self.value, bool)
                or not _finite(self.value)
            ):
                raise ValueError(f"quality expectation {self.rule} requires a finite number")
        elif self.rule == "min_distinct":
            if not isinstance(self.value, int) or isinstance(self.value, bool) or self.value < 1:
                raise ValueError("min_distinct requires a positive integer value")
        elif self.value is not None:
            raise ValueError(f"quality expectation {self.rule} does not accept a value")

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "column": self.column,
            "rule": self.rule,
            "severity": self.severity,
            "value": self.value,
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @property
    def digest(self) -> str:
        return sha256(encode_canonical_json(self.to_payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class QualitySuite:
    id: str
    version: int
    expectations: tuple[QualityExpectation, ...]
    schema: str = "ronin.ml-quality-suite/v1"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.id, str)
            or not self.id
            or self.id != self.id.strip()
            or len(self.id) > 256
        ):
            raise ValueError("quality suite id must be trimmed text of at most 256 characters")
        if self.schema != "ronin.ml-quality-suite/v1":
            raise ValueError("unsupported quality suite schema")
        validate_catalog_version(self.version, "quality suite")
        if (
            not isinstance(self.expectations, tuple)
            or not self.expectations
            or len(self.expectations) > 64
            or any(not isinstance(item, QualityExpectation) for item in self.expectations)
            or len({item.id for item in self.expectations}) != len(self.expectations)
        ):
            raise ValueError("quality suite requires 1 to 64 uniquely identified expectations")
        object.__setattr__(
            self, "expectations", tuple(sorted(self.expectations, key=lambda item: item.id))
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "id": self.id,
            "version": self.version,
            "expectations": [item.to_payload() for item in self.expectations],
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @property
    def digest(self) -> str:
        return sha256(encode_canonical_json(self.to_payload())).hexdigest()

    @classmethod
    def from_payload(cls, payload: object) -> QualitySuite:
        if (
            not isinstance(payload, Mapping)
            or set(payload) != {"schema", "id", "version", "expectations"}
            or not isinstance(payload.get("schema"), str)
            or not isinstance(payload.get("id"), str)
            or not isinstance(payload.get("version"), int)
            or isinstance(payload.get("version"), bool)
            or not isinstance(payload.get("expectations"), list)
        ):
            raise ValueError("quality suite has invalid shape")
        expectations: list[QualityExpectation] = []
        for item in cast(list[object], payload["expectations"]):
            if not isinstance(item, Mapping) or set(item) != {
                "id",
                "column",
                "rule",
                "severity",
                "value",
            }:
                raise ValueError("quality expectation has invalid shape")
            expectations.append(
                QualityExpectation(
                    cast(str, item["id"]),
                    cast(str, item["column"]),
                    cast(str, item["rule"]),
                    cast(str, item["severity"]),
                    cast(int | float | None, item["value"]),
                )
            )
        return cls(
            cast(str, payload["id"]),
            cast(int, payload["version"]),
            tuple(expectations),
            cast(str, payload["schema"]),
        )

    @classmethod
    def from_json(cls, payload: str) -> QualitySuite:
        return cls.from_payload(decode_canonical_json(payload))


@dataclass(frozen=True, slots=True)
class QualityExpectationResult:
    id: str
    column: str
    rule: str
    severity: str
    passed: bool
    message: str

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "column": self.column,
            "rule": self.rule,
            "severity": self.severity,
            "passed": self.passed,
            "message": self.message,
        }


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    dtype: str
    row_count: int
    null_count: int
    distinct_count: int
    constant: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "row_count": self.row_count,
            "null_count": self.null_count,
            "distinct_count": self.distinct_count,
            "constant": self.constant,
        }


@dataclass(frozen=True)
class QualityReport:
    row_count: int
    profiles: tuple[ColumnProfile, ...]
    warnings: tuple[str, ...]
    failures: tuple[str, ...]
    suite_id: str | None = None
    suite_version: int | None = None
    expectations: tuple[QualityExpectationResult, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.failures

    def to_payload(self) -> dict[str, object]:
        return {
            "row_count": self.row_count,
            "passed": self.passed,
            "profiles": [profile.to_payload() for profile in self.profiles],
            "warnings": list(self.warnings),
            "failures": list(self.failures),
            "suite": (
                {"id": self.suite_id, "version": self.suite_version}
                if self.suite_id is not None
                else None
            ),
            "expectations": [item.to_payload() for item in self.expectations],
        }


def profile_and_validate(
    lab: Lab,
    rows: list[dict[str, Any]],
    *,
    min_rows: int = 4,
    suite: QualitySuite | None = None,
) -> QualityReport:
    validate_quality_suite(lab, suite)
    names = ([lab.target] if lab.target is not None else []) + [
        feature.column for feature in lab.features
    ]
    profiles: list[ColumnProfile] = []
    warnings: list[str] = []
    failures: list[str] = []
    if len(rows) < min_rows:
        failures.append(f"dataset has {len(rows)} rows; minimum is {min_rows}")
    for name in names:
        values = [row.get(name) for row in rows]
        non_null = [value for value in values if value is not None]
        distinct = {_distinct_value_key(value) for value in non_null}
        profile = ColumnProfile(
            name=name,
            dtype=type(non_null[0]).__name__ if non_null else "unknown",
            row_count=len(rows),
            null_count=len(values) - len(non_null),
            distinct_count=len(distinct),
            constant=len(distinct) <= 1,
        )
        profiles.append(profile)
        if profile.null_count:
            warnings.append(f"column {name!r} contains {profile.null_count} null values")
        if profile.constant:
            warnings.append(f"column {name!r} is constant")
    target_name = lab.target
    target_profile = next((profile for profile in profiles if profile.name == target_name), None)
    if target_profile is not None and lab.task == "classification" and target_name is not None:
        if target_profile.distinct_count < 2:
            failures.append("classification target must contain at least two classes")
        counts: dict[object, int] = {}
        for row in rows:
            key = _distinct_value_key(row.get(target_name))
            counts[key] = counts.get(key, 0) + 1
        if counts and min(counts.values()) < 2:
            failures.append("each classification class must contain at least two rows")
    expectation_results: list[QualityExpectationResult] = []
    if suite is not None:
        for expectation in suite.expectations:
            values = [row.get(expectation.column) for row in rows]
            passed = _expectation_passes(expectation, values)
            message = (
                "expectation passed"
                if passed
                else f"expectation {expectation.id!r} failed for column {expectation.column!r}"
            )
            expectation_results.append(
                QualityExpectationResult(
                    expectation.id,
                    expectation.column,
                    expectation.rule,
                    expectation.severity,
                    passed,
                    message,
                )
            )
            if not passed:
                messages = warnings if expectation.severity == "warning" else failures
                messages.append(message)
    return QualityReport(
        len(rows),
        tuple(profiles),
        tuple(warnings),
        tuple(failures),
        suite.id if suite is not None else None,
        suite.version if suite is not None else None,
        tuple(expectation_results),
    )


def validate_quality_suite(lab: Lab, suite: QualitySuite | None) -> None:
    if suite is None:
        return
    allowed_columns = {feature.column for feature in lab.features}
    if lab.target is not None:
        allowed_columns.add(lab.target)
    for expectation in suite.expectations:
        if expectation.column not in allowed_columns:
            raise ValueError(
                f"quality expectation references a column outside this Lab: {expectation.column}"
            )


def _expectation_passes(expectation: QualityExpectation, values: list[object]) -> bool:
    if expectation.rule == "not_null":
        return bool(values) and all(value is not None for value in values)
    if expectation.rule == "numeric":
        return bool(values) and all(
            isinstance(value, (int, float)) and not isinstance(value, bool) and _finite(value)
            for value in values
        )
    if expectation.rule in {"min", "max"}:
        if not values or any(
            not isinstance(value, (int, float)) or isinstance(value, bool) or not _finite(value)
            for value in values
        ):
            return False
        threshold = cast(int | float, expectation.value)
        return all(
            value >= threshold if expectation.rule == "min" else value <= threshold
            for value in cast(list[int | float], values)
        )
    if expectation.rule == "min_distinct":
        return len({_distinct_value_key(value) for value in values if value is not None}) >= cast(
            int, expectation.value
        )
    return False


def _distinct_value_key(value: object) -> object:
    """Create a stable, type-aware key for JSON-compatible distinct values."""
    if value is None:
        return ("null",)
    if isinstance(value, bool):
        return ("boolean", value)
    if isinstance(value, int):
        return ("number", Decimal(value))
    if isinstance(value, float):
        if not math.isfinite(value):
            return ("non-finite-number", repr(value))
        return ("number", Decimal(str(value)))
    if isinstance(value, str):
        return ("string", value)
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            return ("other", type(value).__qualname__, repr(value))
        return (
            "object",
            tuple(sorted((key, _distinct_value_key(child)) for key, child in value.items())),
        )
    if isinstance(value, (list, tuple)):
        return ("array", tuple(_distinct_value_key(child) for child in value))
    return ("other", type(value).__qualname__, repr(value))


def _finite(value: int | float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:
        return False
