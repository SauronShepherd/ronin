"""Bounded, explainable anomaly detection hooks for telemetry series."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnomalyResult:
    schema: str
    metric_name: str
    value: float
    baseline: float
    deviation: float
    threshold: float
    anomalous: bool
    reason: str

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "metric_name": self.metric_name,
            "value": self.value,
            "baseline": self.baseline,
            "deviation": self.deviation,
            "threshold": self.threshold,
            "anomalous": self.anomalous,
            "reason": self.reason,
        }


def detect_anomaly(
    metric_name: str,
    history: tuple[float, ...],
    value: float,
    *,
    threshold: float = 3.0,
) -> AnomalyResult:
    """Compare one value with a bounded median/MAD baseline."""
    if not metric_name or metric_name != metric_name.strip() or "\x00" in metric_name:
        raise ValueError("metric_name must be non-empty and trimmed")
    if not history or len(history) > 10_000:
        raise ValueError("anomaly history must contain between 1 and 10000 values")
    if isinstance(threshold, bool) or not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("anomaly threshold must be positive and finite")
    values = (*history, value)
    if any(isinstance(item, bool) or not math.isfinite(item) for item in values):
        raise ValueError("anomaly values must be finite")
    ordered = sorted(history)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        baseline = ordered[middle]
    else:
        baseline = ordered[middle - 1] / 2 + ordered[middle] / 2
    deviations = tuple(abs(item - baseline) for item in history)
    if any(not math.isfinite(item) for item in deviations):
        raise ValueError("anomaly values are numerically unstable")
    ordered_deviations = sorted(deviations)
    middle = len(ordered_deviations) // 2
    if len(ordered_deviations) % 2:
        mad = ordered_deviations[middle]
    else:
        mad = ordered_deviations[middle - 1] / 2 + ordered_deviations[middle] / 2
    scale = mad if mad > 0 else max(abs(baseline) * 0.01, 1.0)
    deviation = abs(value - baseline) / scale
    if not all(math.isfinite(item) for item in (baseline, mad, scale, deviation)):
        raise ValueError("anomaly calculation is numerically unstable")
    anomalous = deviation > threshold
    reason = (
        f"value deviates {deviation:.3f} scaled units from median baseline"
        if anomalous
        else "value is within configured deviation threshold"
    )
    return AnomalyResult(
        "ronin.observability.anomaly/v1",
        metric_name,
        value,
        baseline,
        deviation,
        threshold,
        anomalous,
        reason,
    )


__all__ = ("AnomalyResult", "detect_anomaly")
