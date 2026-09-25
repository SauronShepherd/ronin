"""Durable SQLite telemetry and alert state store for the reference profile."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from studio_orchestrator import Instant

from .contracts import AlertInstance, AlertRule, MetricKind, MetricPoint, TelemetryEvent
from .notifications import NotificationIntent


class SqliteTelemetryStore:
    """Persist normalized metrics/events/rules without coupling to an exporter backend."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS telemetry_metrics (
                    metric_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    value REAL NOT NULL,
                    unit TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    attributes_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS telemetry_metrics_name_time_idx
                    ON telemetry_metrics(name, observed_at);
                CREATE TABLE IF NOT EXISTS telemetry_events (
                    event_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    message TEXT NOT NULL,
                    attributes_json TEXT NOT NULL,
                    trace_id TEXT,
                    span_id TEXT
                );
                CREATE INDEX IF NOT EXISTS telemetry_events_name_time_idx
                    ON telemetry_events(name, occurred_at);
                CREATE TABLE IF NOT EXISTS alert_rules (
                    rule_id TEXT PRIMARY KEY,
                    rule_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS alert_instances (
                    rule_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    PRIMARY KEY(rule_id, fingerprint)
                );
                CREATE TABLE IF NOT EXISTS notification_intents (
                    notification_id TEXT PRIMARY KEY,
                    intent_json TEXT NOT NULL,
                    delivered_at TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    next_attempt_at TEXT
                );
                """
            )
            for statement in (
                "ALTER TABLE notification_intents ADD COLUMN attempt_count "
                "INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE notification_intents ADD COLUMN last_error TEXT",
                "ALTER TABLE notification_intents ADD COLUMN next_attempt_at TEXT",
            ):
                try:
                    connection.execute(statement)
                except sqlite3.OperationalError as exc:
                    if "duplicate column name" not in str(exc).lower():
                        raise
            connection.commit()
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def put_notification_intent(self, intent: NotificationIntent) -> NotificationIntent:
        payload = json.dumps(
            {
                "id": intent.id,
                "kind": intent.kind,
                "title": intent.title,
                "body": intent.body,
                "created_at": str(intent.created_at),
                "attributes": list(intent.attributes),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO notification_intents(notification_id,intent_json) VALUES (?,?) "
                "ON CONFLICT(notification_id) DO NOTHING",
                (intent.id, payload),
            )
            connection.commit()
            return intent
        finally:
            connection.close()

    def list_pending_notification_intents(
        self, *, limit: int = 100, now: Instant | str | None = None
    ) -> tuple[NotificationIntent, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("notification limit must be between 1 and 1000")
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT intent_json FROM notification_intents WHERE delivered_at IS NULL "
                "AND (next_attempt_at IS NULL OR next_attempt_at <= ?) "
                "ORDER BY notification_id LIMIT ?",
                (
                    (
                        str(Instant(now))
                        if now is not None
                        else datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    ),
                    limit,
                ),
            ).fetchall()
            return tuple(self._notification_from_json(row[0]) for row in rows)
        finally:
            connection.close()

    def mark_notification_delivered(
        self, notification_id: str, *, delivered_at: Instant | str
    ) -> bool:
        connection = self._connect()
        try:
            cursor = connection.execute(
                "UPDATE notification_intents SET delivered_at=? "
                "WHERE notification_id=? AND delivered_at IS NULL",
                (str(Instant(delivered_at)), notification_id),
            )
            connection.commit()
            return cursor.rowcount == 1
        finally:
            connection.close()

    def record_notification_failure(
        self,
        notification_id: str,
        *,
        error: str,
        retry_at: Instant | str,
    ) -> bool:
        if not error or error != error.strip() or "\x00" in error:
            raise ValueError("notification error must be non-empty and trimmed")
        connection = self._connect()
        try:
            cursor = connection.execute(
                "UPDATE notification_intents SET attempt_count=attempt_count+1, "
                "last_error=?, next_attempt_at=? "
                "WHERE notification_id=? AND delivered_at IS NULL",
                (error, str(Instant(retry_at)), notification_id),
            )
            connection.commit()
            return cursor.rowcount == 1
        finally:
            connection.close()

    def notification_delivery_state(self, notification_id: str) -> dict[str, object] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT delivered_at,attempt_count,last_error,next_attempt_at "
                "FROM notification_intents WHERE notification_id=?",
                (notification_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return {
            "delivered_at": row[0],
            "attempt_count": int(row[1]),
            "last_error": row[2],
            "next_attempt_at": row[3],
        }

    @staticmethod
    def _notification_from_json(payload: str) -> NotificationIntent:
        value = json.loads(payload)
        return NotificationIntent(
            value["id"],
            value["kind"],
            value["title"],
            value["body"],
            Instant(value["created_at"]),
            tuple(tuple(item) for item in value["attributes"]),
        )

    @staticmethod
    def _attributes_json(attributes: tuple[tuple[str, str], ...]) -> str:
        return json.dumps(dict(attributes), sort_keys=True, separators=(",", ":"))

    @classmethod
    def _metric_id(cls, point: MetricPoint) -> str:
        digest = hashlib.sha256(
            (
                f"{point.name}\n{point.kind}\n{point.observed_at}\n{point.value!r}\n{point.unit}\n"
                + cls._attributes_json(point.attributes)
            ).encode("utf-8")
        ).hexdigest()
        return f"metric-{digest}"

    @classmethod
    def _event_id(cls, event: TelemetryEvent) -> str:
        digest = hashlib.sha256(
            (
                f"{event.name}\n{event.occurred_at}\n{event.severity}\n{event.message}\n"
                + cls._attributes_json(event.attributes)
                + f"\n{event.trace_id or ''}\n{event.span_id or ''}"
            ).encode("utf-8")
        ).hexdigest()
        return f"event-{digest}"

    def record_metric(self, point: MetricPoint) -> MetricPoint:
        connection = self._connect()
        try:
            connection.execute(
                "INSERT OR IGNORE INTO telemetry_metrics("
                "metric_id,name,value,unit,kind,observed_at,attributes_json) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    self._metric_id(point),
                    point.name,
                    point.value,
                    point.unit,
                    point.kind,
                    str(point.observed_at),
                    self._attributes_json(point.attributes),
                ),
            )
            connection.commit()
            return point
        finally:
            connection.close()

    def list_metrics(self, *, limit: int = 10_000) -> tuple[MetricPoint, ...]:
        """List persisted metrics in deterministic order with a hard bound."""
        if limit < 1 or limit > 100_000:
            raise ValueError("metric list limit must be between 1 and 100000")
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT name,value,unit,kind,observed_at,attributes_json FROM telemetry_metrics "
                "ORDER BY name, observed_at, metric_id LIMIT ?",
                (limit,),
            ).fetchall()
            result: list[MetricPoint] = []
            for row in rows:
                attrs_raw = json.loads(row[5])
                if not isinstance(attrs_raw, dict):
                    raise ValueError("persisted metric attributes are invalid")
                result.append(
                    MetricPoint(
                        str(row[0]),
                        float(row[1]),
                        str(row[2]),
                        cast(MetricKind, str(row[3])),
                        Instant(str(row[4])),
                        tuple(sorted((str(key), str(value)) for key, value in attrs_raw.items())),
                    )
                )
            return tuple(result)
        finally:
            connection.close()

    def record_event(self, event: TelemetryEvent) -> TelemetryEvent:
        connection = self._connect()
        try:
            connection.execute(
                "INSERT OR IGNORE INTO telemetry_events("
                "event_id,name,severity,occurred_at,message,attributes_json,trace_id,span_id) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    self._event_id(event),
                    event.name,
                    event.severity,
                    str(event.occurred_at),
                    event.message,
                    self._attributes_json(event.attributes),
                    event.trace_id,
                    event.span_id,
                ),
            )
            connection.commit()
            return event
        finally:
            connection.close()

    def latest_metric(
        self,
        name: str,
        *,
        attribute_filters: tuple[tuple[str, str], ...] = (),
    ) -> MetricPoint | None:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT value,unit,kind,observed_at,attributes_json FROM telemetry_metrics "
                "WHERE name=? ORDER BY observed_at DESC, metric_id DESC LIMIT 10000",
                (name,),
            ).fetchall()
            filters = dict(attribute_filters)
            for row in rows:
                attrs_raw = json.loads(row[4])
                if not isinstance(attrs_raw, dict):
                    raise ValueError("persisted metric attributes are invalid")
                attrs = {str(key): str(value) for key, value in attrs_raw.items()}
                if any(attrs.get(key) != value for key, value in filters.items()):
                    continue
                return MetricPoint(
                    name,
                    float(row[0]),
                    str(row[1]),
                    str(row[2]),  # type: ignore[arg-type]
                    Instant(row[3]),
                    tuple(sorted(attrs.items())),
                )
            return None
        finally:
            connection.close()

    def put_alert_rule(self, rule: AlertRule) -> AlertRule:
        payload = json.dumps(
            {
                "id": rule.id,
                "name": rule.name,
                "metric_name": rule.metric_name,
                "operator": rule.operator,
                "threshold": rule.threshold,
                "attribute_filters": dict(rule.attribute_filters),
                "enabled": rule.enabled,
                "cooldown_seconds": rule.cooldown_seconds,
                "pending_seconds": rule.pending_seconds,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO alert_rules(rule_id,rule_json) VALUES (?,?) "
                "ON CONFLICT(rule_id) DO UPDATE SET rule_json=excluded.rule_json",
                (rule.id, payload),
            )
            connection.commit()
            return rule
        finally:
            connection.close()

    def list_alert_rules(self) -> tuple[AlertRule, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT rule_json FROM alert_rules ORDER BY rule_id"
            ).fetchall()
            result: list[AlertRule] = []
            for (payload,) in rows:
                value = json.loads(payload)
                filters = value["attribute_filters"]
                result.append(
                    AlertRule(
                        value["id"],
                        value["name"],
                        value["metric_name"],
                        value["operator"],
                        float(value["threshold"]),
                        tuple(sorted((str(key), str(val)) for key, val in filters.items())),
                        bool(value["enabled"]),
                        int(value.get("cooldown_seconds", 0)),
                        int(value.get("pending_seconds", 0)),
                    )
                )
            return tuple(result)
        finally:
            connection.close()

    def get_alert_instance(self, rule_id: str, fingerprint: str) -> AlertInstance | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT state_json FROM alert_instances WHERE rule_id=? AND fingerprint=?",
                (rule_id, fingerprint),
            ).fetchone()
            if row is None:
                return None
            value = json.loads(row[0])
            resolved = value["resolved_at"]
            acknowledged = value.get("acknowledged_at")
            return AlertInstance(
                value["rule_id"],
                value["fingerprint"],
                value["status"],
                float(value["value"]),
                Instant(value["opened_at"]),
                Instant(value["updated_at"]),
                None if resolved is None else Instant(resolved),
                None if acknowledged is None else Instant(acknowledged),
            )
        finally:
            connection.close()

    def list_alert_instances(self, *, limit: int = 100) -> tuple[AlertInstance, ...]:
        """Return a bounded deterministic inventory of persisted alert states."""
        if not 1 <= limit <= 1000:
            raise ValueError("alert instance limit must be between 1 and 1000")
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT rule_id,fingerprint FROM alert_instances "
                "ORDER BY rule_id,fingerprint LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            instance
            for rule_id, fingerprint in rows
            if (instance := self.get_alert_instance(rule_id, fingerprint)) is not None
        )

    def put_alert_instance(self, instance: AlertInstance) -> AlertInstance:
        payload = json.dumps(
            {
                "rule_id": instance.rule_id,
                "fingerprint": instance.fingerprint,
                "status": instance.status,
                "value": instance.value,
                "opened_at": str(instance.opened_at),
                "updated_at": str(instance.updated_at),
                "resolved_at": None if instance.resolved_at is None else str(instance.resolved_at),
                "acknowledged_at": (
                    None if instance.acknowledged_at is None else str(instance.acknowledged_at)
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO alert_instances(rule_id,fingerprint,state_json) VALUES (?,?,?) "
                "ON CONFLICT(rule_id,fingerprint) DO UPDATE SET state_json=excluded.state_json",
                (instance.rule_id, instance.fingerprint, payload),
            )
            connection.commit()
            return instance
        finally:
            connection.close()

    def acknowledge_alert(
        self, rule_id: str, fingerprint: str, *, acknowledged_at: Instant | str
    ) -> AlertInstance | None:
        """Persist an idempotent acknowledgement for an active alert."""
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT state_json FROM alert_instances WHERE rule_id=? AND fingerprint=?",
                (rule_id, fingerprint),
            ).fetchone()
            if row is None:
                return None
            value = json.loads(row[0])
            if value["status"] == "resolved":
                return self.get_alert_instance(rule_id, fingerprint)
            value["acknowledged_at"] = str(Instant(acknowledged_at))
            payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
            connection.execute(
                "UPDATE alert_instances SET state_json=? WHERE rule_id=? AND fingerprint=?",
                (payload, rule_id, fingerprint),
            )
            connection.commit()
            return self.get_alert_instance(rule_id, fingerprint)
        finally:
            connection.close()


__all__ = ("SqliteTelemetryStore",)
