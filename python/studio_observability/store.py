"""Durable SQLite telemetry and alert state store for the reference profile."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from studio_orchestrator import Instant

from .contracts import AlertInstance, AlertRule, MetricPoint, TelemetryEvent


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
                """
            )
            connection.commit()
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    @staticmethod
    def _attributes_json(attributes: tuple[tuple[str, str], ...]) -> str:
        return json.dumps(dict(attributes), sort_keys=True, separators=(",", ":"))

    @classmethod
    def _metric_id(cls, point: MetricPoint) -> str:
        digest = hashlib.sha256(
            (
                f"{point.name}\n{point.observed_at}\n{point.value!r}\n{point.unit}\n"
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
                "WHERE name=? ORDER BY observed_at DESC, metric_id DESC",
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
            rows = connection.execute("SELECT rule_json FROM alert_rules ORDER BY rule_id").fetchall()
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
            return AlertInstance(
                value["rule_id"],
                value["fingerprint"],
                value["status"],
                float(value["value"]),
                Instant(value["opened_at"]),
                Instant(value["updated_at"]),
                None if resolved is None else Instant(resolved),
            )
        finally:
            connection.close()

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


__all__ = ("SqliteTelemetryStore",)
