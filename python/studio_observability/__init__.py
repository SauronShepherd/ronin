"""Observability, alert-state and notification primitives for Ronin Public v1."""

from .alerts import AlertTelemetryStore, AlertTransition, evaluate_alert
from .contracts import (
    AlertInstance,
    AlertOperator,
    AlertRule,
    AlertStatus,
    MetricKind,
    MetricPoint,
    Severity,
    TelemetryEvent,
)
from .instrumentation import instrument_execution
from .notifications import NotificationIntent, NotificationSink, alert_notification
from .prometheus import prometheus_text
from .store import SqliteTelemetryStore
from .webhook import WebhookNotificationError, WebhookNotificationSink

__all__ = (
    "AlertInstance",
    "AlertOperator",
    "AlertRule",
    "AlertStatus",
    "AlertTelemetryStore",
    "AlertTransition",
    "MetricKind",
    "MetricPoint",
    "NotificationIntent",
    "NotificationSink",
    "Severity",
    "SqliteTelemetryStore",
    "TelemetryEvent",
    "WebhookNotificationError",
    "WebhookNotificationSink",
    "prometheus_text",
    "instrument_execution",
    "alert_notification",
    "evaluate_alert",
)
