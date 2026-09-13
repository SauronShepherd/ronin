"""Durable alert state evaluation over normalized telemetry metrics."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from studio_orchestrator import Instant

from .contracts import AlertInstance, AlertRule, MetricPoint


@runtime_checkable
class AlertTelemetryStore(Protocol):
    def latest_metric(
        self,
        name: str,
        *,
        attribute_filters: tuple[tuple[str, str], ...] = (),
    ) -> MetricPoint | None: ...

    def get_alert_instance(self, rule_id: str, fingerprint: str) -> AlertInstance | None: ...

    def put_alert_instance(self, instance: AlertInstance) -> AlertInstance: ...


@dataclass(frozen=True, slots=True)
class AlertTransition:
    rule: AlertRule
    metric: MetricPoint | None
    previous: AlertInstance | None
    current: AlertInstance | None
    changed: bool


def _matches(rule: AlertRule, value: float) -> bool:
    if rule.operator == "gt":
        return value > rule.threshold
    if rule.operator == "gte":
        return value >= rule.threshold
    if rule.operator == "lt":
        return value < rule.threshold
    if rule.operator == "lte":
        return value <= rule.threshold
    if rule.operator == "eq":
        return value == rule.threshold
    if rule.operator == "ne":
        return value != rule.threshold
    raise AssertionError(f"unsupported alert operator: {rule.operator}")


def _fingerprint(rule: AlertRule) -> str:
    source = "\n".join(
        (
            rule.id,
            rule.metric_name,
            *(f"{key}={value}" for key, value in rule.attribute_filters),
        )
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def evaluate_alert(
    store: AlertTelemetryStore,
    rule: AlertRule,
    *,
    now: Instant | str,
) -> AlertTransition:
    """Evaluate the latest matching metric and persist only meaningful state transitions."""

    current_time = Instant(now)
    fingerprint = _fingerprint(rule)
    previous = store.get_alert_instance(rule.id, fingerprint)
    if not rule.enabled:
        return AlertTransition(rule, None, previous, previous, False)

    metric = store.latest_metric(
        rule.metric_name,
        attribute_filters=rule.attribute_filters,
    )
    if metric is None:
        return AlertTransition(rule, None, previous, previous, False)

    firing = _matches(rule, metric.value)
    if firing:
        if previous is None or previous.status == "resolved":
            opened_at = current_time
            current = AlertInstance(
                rule.id,
                fingerprint,
                "open",
                metric.value,
                opened_at,
                current_time,
            )
            store.put_alert_instance(current)
            return AlertTransition(rule, metric, previous, current, True)
        current = AlertInstance(
            rule.id,
            fingerprint,
            "open",
            metric.value,
            previous.opened_at,
            current_time,
        )
        changed = current.value != previous.value
        if changed:
            store.put_alert_instance(current)
        return AlertTransition(rule, metric, previous, current, changed)

    if previous is not None and previous.status == "open":
        current = AlertInstance(
            rule.id,
            fingerprint,
            "resolved",
            metric.value,
            previous.opened_at,
            current_time,
            current_time,
        )
        store.put_alert_instance(current)
        return AlertTransition(rule, metric, previous, current, True)
    return AlertTransition(rule, metric, previous, previous, False)


__all__ = ("AlertTelemetryStore", "AlertTransition", "evaluate_alert")
