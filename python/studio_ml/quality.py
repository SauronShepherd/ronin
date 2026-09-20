"""Tabular profiling and pre-training quality gates for Machine Learning Studio."""
# ruff: noqa: E501

from dataclasses import dataclass
from typing import Any

from .domain import Lab


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
        }


def profile_and_validate(
    lab: Lab, rows: list[dict[str, Any]], *, min_rows: int = 4
) -> QualityReport:
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
        distinct = {repr(value) for value in non_null}
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
    target = next((profile for profile in profiles if profile.name == lab.target), None)
    if target is not None and lab.task == "classification":
        if target.distinct_count < 2:
            failures.append("classification target must contain at least two classes")
        counts: dict[str, int] = {}
        for row in rows:
            key = repr(row.get(lab.target))
            counts[key] = counts.get(key, 0) + 1
        if counts and min(counts.values()) < 2:
            failures.append("each classification class must contain at least two rows")
    return QualityReport(len(rows), tuple(profiles), tuple(warnings), tuple(failures))
