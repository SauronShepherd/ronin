"""Bounded, provider-neutral numeric drift comparison for ML reference data."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from statistics import fmean, pvariance
from typing import Literal


@dataclass(frozen=True, slots=True)
class NumericDrift:
    """Deterministic summary of one numeric feature across two data windows."""

    feature: str
    baseline_count: int
    current_count: int
    baseline_mean: float
    current_mean: float
    mean_delta: float
    baseline_variance: float
    current_variance: float
    variance_delta: float

    def to_payload(self) -> dict[str, object]:
        return {
            "feature": self.feature,
            "baseline_count": self.baseline_count,
            "current_count": self.current_count,
            "baseline_mean": self.baseline_mean,
            "current_mean": self.current_mean,
            "mean_delta": self.mean_delta,
            "baseline_variance": self.baseline_variance,
            "current_variance": self.current_variance,
            "variance_delta": self.variance_delta,
        }


@dataclass(frozen=True, slots=True)
class DriftThreshold:
    """Absolute feature-level thresholds for a drift assessment."""

    feature: str
    mean_delta: float
    variance_delta: float

    def __post_init__(self) -> None:
        if not self.feature or self.feature != self.feature.strip():
            raise ValueError("drift threshold feature must be non-empty and trimmed")
        if self.mean_delta < 0 or self.variance_delta < 0:
            raise ValueError("drift thresholds must not be negative")


@dataclass(frozen=True, slots=True)
class DriftAssessment:
    """Stable threshold decision over one or more numeric drift summaries."""

    status: Literal["ok", "drifted"]
    drifted_features: tuple[str, ...]

    def __post_init__(self) -> None:
        features = tuple(sorted(set(self.drifted_features)))
        if self.status == "ok" and features:
            raise ValueError("an ok drift assessment cannot contain drifted features")
        if self.status == "drifted" and not features:
            raise ValueError("a drifted assessment requires drifted features")
        object.__setattr__(self, "drifted_features", features)


def assess_numeric_drift(
    summaries: tuple[NumericDrift, ...], thresholds: tuple[DriftThreshold, ...]
) -> DriftAssessment:
    """Evaluate absolute mean/variance deltas against explicit feature thresholds."""
    threshold_map = {item.feature: item for item in thresholds}
    if len(threshold_map) != len(thresholds):
        raise ValueError("drift thresholds must contain unique features")
    summary_map = {item.feature: item for item in summaries}
    if len(summary_map) != len(summaries):
        raise ValueError("drift summaries must contain unique features")
    drifted = tuple(
        feature
        for feature, threshold in sorted(threshold_map.items())
        if feature not in summary_map
        or abs(summary_map[feature].mean_delta) > threshold.mean_delta
        or abs(summary_map[feature].variance_delta) > threshold.variance_delta
    )
    return DriftAssessment("drifted", drifted) if drifted else DriftAssessment("ok", ())


def compare_numeric_drift(
    baseline: Sequence[Mapping[str, object]],
    current: Sequence[Mapping[str, object]],
    features: tuple[str, ...],
    *,
    max_rows: int = 100_000,
) -> tuple[NumericDrift, ...]:
    """Compare finite numeric feature windows with deterministic bounded semantics."""
    if not features or len(set(features)) != len(features):
        raise ValueError("drift features must be non-empty and unique")
    if max_rows < 1 or len(baseline) > max_rows or len(current) > max_rows:
        raise ValueError("drift input exceeds max_rows")
    result: list[NumericDrift] = []
    for feature in features:
        baseline_values = _values(baseline, feature)
        current_values = _values(current, feature)
        if not baseline_values or not current_values:
            raise ValueError(f"drift feature requires values in both windows: {feature}")
        baseline_mean = fmean(baseline_values)
        current_mean = fmean(current_values)
        baseline_variance = pvariance(baseline_values)
        current_variance = pvariance(current_values)
        result.append(
            NumericDrift(
                feature,
                len(baseline_values),
                len(current_values),
                baseline_mean,
                current_mean,
                current_mean - baseline_mean,
                baseline_variance,
                current_variance,
                current_variance - baseline_variance,
            )
        )
    return tuple(result)


def _values(rows: Sequence[Mapping[str, object]], feature: str) -> tuple[float, ...]:
    if not feature or feature != feature.strip():
        raise ValueError("drift feature names must be non-empty and trimmed")
    values: list[float] = []
    for row in rows:
        value = row.get(feature)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value):
            raise ValueError(f"drift feature values must be finite numbers: {feature}")
        values.append(float(value))
    return tuple(values)


__all__ = (
    "DriftAssessment",
    "DriftThreshold",
    "NumericDrift",
    "assess_numeric_drift",
    "compare_numeric_drift",
)
