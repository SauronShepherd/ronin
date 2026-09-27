"""Bounded, explainable anomaly detection hooks for telemetry series."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median


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
    if threshold <= 0 or threshold != threshold or abs(threshold) == float("inf"):
        raise ValueError("anomaly threshold must be positive and finite")
    values = (*history, value)
    if any(item != item or abs(item) == float("inf") for item in values):
        raise ValueError("anomaly values must be finite")
    baseline = median(history)
    mad = median(tuple(abs(item - baseline) for item in history))
    scale = mad if mad > 0 else max(abs(baseline) * 0.01, 1.0)
    deviation = abs(value - baseline) / scale
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
