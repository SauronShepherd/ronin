"""Integration adapter from quality runs into the common telemetry engine."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from studio_orchestrator import Instant

from .alerts import AlertTelemetryStore, AlertTransition, evaluate_alert
from .contracts import AlertRule, MetricPoint


class _QualityResult(Protocol):
    rule_id: object
    status: str


class _QualityRun(Protocol):
    asset: object
    id: object
    status: str
    results: tuple[_QualityResult, ...]


def record_quality_metrics(
    run: _QualityRun,
    record_metric: Callable[[MetricPoint], object],
    *,
    observed_at: Instant | str,
) -> tuple[MetricPoint, ...]:
    """Materialize a quality run as metrics consumable by ``evaluate_alert``."""
    observed = Instant(observed_at)
    points = tuple(
        MetricPoint(
            "quality.rule.failure",
            1.0 if result.status in {"failed", "error"} else 0.0,
            "boolean",
            "gauge",
            observed,
            (("asset", str(run.asset)), ("rule_id", str(result.rule_id))),
        )
        for result in run.results
    ) + (
        MetricPoint(
            "quality.run.failure",
            1.0 if run.status in {"failed", "error"} else 0.0,
            "boolean",
            "gauge",
            observed,
            (("asset", str(run.asset)), ("run_id", str(run.id))),
        ),
    )
    for point in points:
        record_metric(point)
    return points


def evaluate_quality_alerts(
    run: _QualityRun,
    store: AlertTelemetryStore,
    rules: tuple[AlertRule, ...],
    *,
    observed_at: Instant | str,
    record_metric: Callable[[MetricPoint], object] | None = None,
) -> tuple[AlertTransition, ...]:
    """Record a quality run and evaluate matching common alert rules."""
    points = record_quality_metrics(
        run,
        record_metric or store.record_metric,
        observed_at=observed_at,
    )
    transitions: list[AlertTransition] = []
    for rule in rules:
        for point in points:
            if rule.metric_name != point.name:
                continue
            attributes = dict(point.attributes)
            if any(attributes.get(key) != value for key, value in rule.attribute_filters):
                continue
            transitions.append(evaluate_alert(store, rule, now=point.observed_at))
    return tuple(transitions)


__all__ = ("evaluate_quality_alerts", "record_quality_metrics")
