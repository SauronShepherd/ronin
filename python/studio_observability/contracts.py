"""Provider-neutral telemetry and alert contracts for Ronin Public v1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from studio_orchestrator import Instant

MetricKind: TypeAlias = Literal["gauge", "counter"]
Severity: TypeAlias = Literal["debug", "info", "warning", "error", "critical"]
AlertOperator: TypeAlias = Literal["gt", "gte", "lt", "lte", "eq", "ne"]
AlertStatus: TypeAlias = Literal["pending", "firing", "open", "resolved"]


def _text(value: str, name: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    return value


def _attributes(values: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    normalized = tuple(
        sorted(
            (_text(key, "telemetry attribute key"), _text(value, "telemetry attribute value"))
            for key, value in values
        )
    )
    keys = [key for key, _ in normalized]
    if len(keys) != len(set(keys)):
        raise ValueError("telemetry attribute keys must be unique")
    return normalized


@dataclass(frozen=True, slots=True)
class MetricPoint:
    name: str
    value: float
    unit: str
    kind: MetricKind
    observed_at: Instant
    attributes: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _text(self.name, "metric name")
        _text(self.unit, "metric unit")
        if self.kind not in {"gauge", "counter"}:
            raise ValueError("unsupported metric kind")
        if self.value != self.value or self.value in (float("inf"), float("-inf")):
            raise ValueError("metric value must be finite")
        object.__setattr__(self, "observed_at", Instant(self.observed_at))
        object.__setattr__(self, "attributes", _attributes(self.attributes))

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "kind": self.kind,
            "observed_at": str(self.observed_at),
            "attributes": dict(self.attributes),
        }


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    name: str
    severity: Severity
    occurred_at: Instant
    message: str
    attributes: tuple[tuple[str, str], ...] = ()
    trace_id: str | None = None
    span_id: str | None = None

    def __post_init__(self) -> None:
        _text(self.name, "event name")
        if self.severity not in {"debug", "info", "warning", "error", "critical"}:
            raise ValueError("unsupported telemetry severity")
        if not self.message or "\x00" in self.message:
            raise ValueError("telemetry event message must be non-empty")
        object.__setattr__(self, "occurred_at", Instant(self.occurred_at))
        object.__setattr__(self, "attributes", _attributes(self.attributes))
        if self.trace_id is not None:
            _text(self.trace_id, "trace_id")
        if self.span_id is not None:
            _text(self.span_id, "span_id")


@dataclass(frozen=True, slots=True)
class AlertRule:
    id: str
    name: str
    metric_name: str
    operator: AlertOperator
    threshold: float
    attribute_filters: tuple[tuple[str, str], ...] = ()
    enabled: bool = True
    cooldown_seconds: int = 0
    pending_seconds: int = 0

    def __post_init__(self) -> None:
        _text(self.id, "alert rule id")
        _text(self.name, "alert rule name")
        _text(self.metric_name, "alert metric name")
        if self.operator not in {"gt", "gte", "lt", "lte", "eq", "ne"}:
            raise ValueError("unsupported alert operator")
        if self.threshold != self.threshold or self.threshold in (float("inf"), float("-inf")):
            raise ValueError("alert threshold must be finite")
        if self.cooldown_seconds < 0:
            raise ValueError("alert cooldown_seconds must not be negative")
        if self.pending_seconds < 0:
            raise ValueError("alert pending_seconds must not be negative")
        object.__setattr__(self, "attribute_filters", _attributes(self.attribute_filters))

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "metric_name": self.metric_name,
            "operator": self.operator,
            "threshold": self.threshold,
            "attribute_filters": dict(self.attribute_filters),
            "enabled": self.enabled,
            "cooldown_seconds": self.cooldown_seconds,
            "pending_seconds": self.pending_seconds,
        }


@dataclass(frozen=True, slots=True)
class AlertInstance:
    rule_id: str
    fingerprint: str
    status: AlertStatus
    value: float
    opened_at: Instant
    updated_at: Instant
    resolved_at: Instant | None = None
    acknowledged_at: Instant | None = None

    def __post_init__(self) -> None:
        _text(self.rule_id, "alert rule id")
        _text(self.fingerprint, "alert fingerprint")
        if self.status not in {"pending", "firing", "open", "resolved"}:
            raise ValueError("unsupported alert status")
        if self.value != self.value or self.value in (float("inf"), float("-inf")):
            raise ValueError("alert value must be finite")
        object.__setattr__(self, "opened_at", Instant(self.opened_at))
        object.__setattr__(self, "updated_at", Instant(self.updated_at))
        if self.resolved_at is not None:
            object.__setattr__(self, "resolved_at", Instant(self.resolved_at))
        if self.acknowledged_at is not None:
            object.__setattr__(self, "acknowledged_at", Instant(self.acknowledged_at))
        if self.status == "resolved" and self.resolved_at is None:
            raise ValueError("resolved alert requires resolved_at")
        if self.status in {"pending", "firing", "open"} and self.resolved_at is not None:
            raise ValueError("active alert must not have resolved_at")

    @property
    def is_active(self) -> bool:
        """Whether the instance can still transition to resolved."""
        return self.status in {"pending", "firing", "open"}

    def to_payload(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "fingerprint": self.fingerprint,
            "status": self.status,
            "value": self.value,
            "opened_at": str(self.opened_at),
            "updated_at": str(self.updated_at),
            "resolved_at": None if self.resolved_at is None else str(self.resolved_at),
            "acknowledged_at": None if self.acknowledged_at is None else str(self.acknowledged_at),
        }

    @property
    def is_firing(self) -> bool:
        """Whether the alert is currently firing (``open`` is legacy alias)."""
        return self.status in {"firing", "open"}


__all__ = (
    "AlertInstance",
    "AlertOperator",
    "AlertRule",
    "AlertStatus",
    "MetricKind",
    "MetricPoint",
    "Severity",
    "TelemetryEvent",
)
