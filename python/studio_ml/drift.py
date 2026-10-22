"""Bounded, provider-neutral numeric drift comparison for ML reference data."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from statistics import fmean, pvariance
from typing import Literal, cast

from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.canonical_json import encode as encode_canonical_json

from .catalog import validate_catalog_version


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

    def __post_init__(self) -> None:
        if (
            not isinstance(self.feature, str)
            or not self.feature
            or self.feature != self.feature.strip()
        ):
            raise ValueError("drift feature name must be non-empty and trimmed")
        counts = (self.baseline_count, self.current_count)
        if any(
            not isinstance(count, int) or isinstance(count, bool) or count < 1 for count in counts
        ):
            raise ValueError("drift window counts must be positive integers")
        statistics = (
            self.baseline_mean,
            self.current_mean,
            self.mean_delta,
            self.baseline_variance,
            self.current_variance,
            self.variance_delta,
        )
        if any(
            not isinstance(value, (int, float)) or isinstance(value, bool) or not _finite(value)
            for value in statistics
        ):
            raise ValueError("drift statistics must be finite numbers")
        if self.baseline_variance < 0 or self.current_variance < 0:
            raise ValueError("drift variances must not be negative")
        mean_delta = self.current_mean - self.baseline_mean
        variance_delta = self.current_variance - self.baseline_variance
        if (
            not _finite(mean_delta)
            or not _finite(variance_delta)
            or self.mean_delta != mean_delta
            or self.variance_delta != variance_delta
        ):
            raise ValueError("drift deltas must match the window statistics")

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
        if (
            not isinstance(self.feature, str)
            or not self.feature
            or self.feature != self.feature.strip()
        ):
            raise ValueError("drift threshold feature must be non-empty and trimmed")
        thresholds = (self.mean_delta, self.variance_delta)
        if any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not _finite(value)
            or value < 0
            for value in thresholds
        ):
            raise ValueError("drift thresholds must not be negative")


@dataclass(frozen=True, slots=True)
class DriftPolicy:
    """Portable, versioned thresholds for a numeric drift assessment."""

    id: str
    version: int
    thresholds: tuple[DriftThreshold, ...]
    schema: str = "ronin.ml-drift-policy/v1"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.id, str)
            or not self.id
            or self.id != self.id.strip()
            or len(self.id) > 256
        ):
            raise ValueError("drift policy id must be trimmed and at most 256 characters")
        if self.schema != "ronin.ml-drift-policy/v1":
            raise ValueError("unsupported drift policy schema")
        validate_catalog_version(self.version, "drift policy")
        if not isinstance(self.thresholds, tuple) or any(
            not isinstance(item, DriftThreshold) for item in self.thresholds
        ):
            raise ValueError("drift policy thresholds must be DriftThreshold values")
        thresholds = tuple(sorted(self.thresholds, key=lambda item: item.feature))
        if not thresholds or len({item.feature for item in thresholds}) != len(thresholds):
            raise ValueError("drift policy thresholds must be non-empty and unique")
        object.__setattr__(self, "thresholds", thresholds)

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "id": self.id,
            "version": self.version,
            "thresholds": [
                {
                    "feature": item.feature,
                    "mean_delta": item.mean_delta,
                    "variance_delta": item.variance_delta,
                }
                for item in self.thresholds
            ],
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_json(cls, payload: str) -> DriftPolicy:
        return cls.from_payload(decode_canonical_json(payload))

    @classmethod
    def from_payload(cls, payload: object) -> DriftPolicy:
        if (
            not isinstance(payload, Mapping)
            or set(payload) != {"schema", "id", "version", "thresholds"}
            or not isinstance(payload.get("schema"), str)
            or not isinstance(payload.get("id"), str)
            or not isinstance(payload.get("version"), int)
            or isinstance(payload.get("version"), bool)
            or not isinstance(payload.get("thresholds"), list)
        ):
            raise ValueError("drift policy has invalid shape")
        thresholds: list[DriftThreshold] = []
        for item in cast(list[object], payload["thresholds"]):
            if not isinstance(item, Mapping) or set(item) != {
                "feature",
                "mean_delta",
                "variance_delta",
            }:
                raise ValueError("drift policy threshold has invalid shape")
            thresholds.append(
                DriftThreshold(
                    cast(str, item["feature"]),
                    cast(float, item["mean_delta"]),
                    cast(float, item["variance_delta"]),
                )
            )
        return cls(
            cast(str, payload["id"]),
            cast(int, payload["version"]),
            tuple(thresholds),
            cast(str, payload["schema"]),
        )


@dataclass(frozen=True, slots=True)
class DriftAssessment:
    """Stable threshold decision over one or more numeric drift summaries."""

    status: Literal["ok", "drifted"]
    drifted_features: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.status, str) or self.status not in {"ok", "drifted"}:
            raise ValueError("unsupported drift assessment status")
        if not isinstance(self.drifted_features, tuple) or any(
            not isinstance(feature, str) or not feature or feature != feature.strip()
            for feature in self.drifted_features
        ):
            raise ValueError("drifted feature names must be non-empty and trimmed")
        if len(set(self.drifted_features)) != len(self.drifted_features):
            raise ValueError("drifted feature names must be unique")
        features = tuple(sorted(self.drifted_features))
        if self.status == "ok" and features:
            raise ValueError("an ok drift assessment cannot contain drifted features")
        if self.status == "drifted" and not features:
            raise ValueError("a drifted assessment requires drifted features")
        object.__setattr__(self, "drifted_features", features)

    def to_payload(self) -> dict[str, object]:
        return {"status": self.status, "drifted_features": list(self.drifted_features)}


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
        try:
            baseline_mean = fmean(baseline_values)
            current_mean = fmean(current_values)
            baseline_variance = pvariance(baseline_values)
            current_variance = pvariance(current_values)
        except OverflowError as exc:
            raise ValueError(f"drift statistics overflow for feature: {feature}") from exc
        mean_delta = current_mean - baseline_mean
        variance_delta = current_variance - baseline_variance
        if not all(
            _finite(value)
            for value in (
                baseline_mean,
                current_mean,
                baseline_variance,
                current_variance,
                mean_delta,
                variance_delta,
            )
        ):
            raise ValueError(f"drift statistics are outside finite numeric range: {feature}")
        result.append(
            NumericDrift(
                feature,
                len(baseline_values),
                len(current_values),
                baseline_mean,
                current_mean,
                mean_delta,
                baseline_variance,
                current_variance,
                variance_delta,
            )
        )
    return tuple(result)


def _values(rows: Sequence[Mapping[str, object]], feature: str) -> tuple[float, ...]:
    if not feature or feature != feature.strip():
        raise ValueError("drift feature names must be non-empty and trimmed")
    values: list[float] = []
    for row in rows:
        value = row.get(feature)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not _finite(value):
            raise ValueError(f"drift feature values must be finite numbers: {feature}")
        try:
            values.append(float(value))
        except OverflowError as exc:
            raise ValueError(f"drift feature values must be finite numbers: {feature}") from exc
    return tuple(values)


def _finite(value: int | float) -> bool:
    try:
        return isfinite(value)
    except OverflowError:
        return False


__all__ = (
    "DriftAssessment",
    "DriftPolicy",
    "DriftThreshold",
    "NumericDrift",
    "assess_numeric_drift",
    "compare_numeric_drift",
)
