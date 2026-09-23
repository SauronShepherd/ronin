"""Observability, alert-state and notification primitives for Ronin Public v1."""

from .alerts import AlertTelemetryStore, AlertTransition, evaluate_alert
from .anomaly import AnomalyResult, detect_anomaly
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
from .dispatcher import (
    NotificationDispatcher,
    NotificationDispatchResult,
    SqliteNotificationIntentStore,
)
from .http import AlertHTTPAdapter, AlertHTTPStore
from .instrumentation import instrument_execution
from .notifications import (
    NotificationIntent,
    NotificationSink,
    alert_notification,
    scheduler_notification,
)
from .prometheus import prometheus_text
from .quality import evaluate_quality_alerts, record_quality_metrics
from .scheduler import SchedulerNotificationStore, persist_terminal_notification
from .smtp import SmtpNotificationError, SmtpNotificationSink
from .store import SqliteTelemetryStore
from .webhook import WebhookNotificationError, WebhookNotificationSink

__all__ = (
    "AlertInstance",
    "AlertOperator",
    "AlertRule",
    "AlertStatus",
    "AlertTelemetryStore",
    "AlertTransition",
    "AlertHTTPAdapter",
    "AlertHTTPStore",
    "AnomalyResult",
    "MetricKind",
    "MetricPoint",
    "NotificationIntent",
    "NotificationSink",
    "NotificationDispatcher",
    "NotificationDispatchResult",
    "SqliteNotificationIntentStore",
    "Severity",
    "SqliteTelemetryStore",
    "SmtpNotificationError",
    "SmtpNotificationSink",
    "TelemetryEvent",
    "WebhookNotificationError",
    "WebhookNotificationSink",
    "prometheus_text",
    "instrument_execution",
    "alert_notification",
    "scheduler_notification",
    "persist_terminal_notification",
    "SchedulerNotificationStore",
    "record_quality_metrics",
    "evaluate_quality_alerts",
    "evaluate_alert",
    "detect_anomaly",
)
