"""Durable scheduler event inbox with routing frozen at event receipt."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from studio_core import Trigger, WorkflowRunId, WorkspaceId
from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.scheduler_events import (
    EventTriggerDefinition,
    EventTriggerId,
    SchedulerEventId,
)
from studio_orchestrator import Instant

from .scheduler_schedule import SchedulerScheduleStore, migrate_scheduler_schedule
from .sqlite import open_database

_EVENTS_SCHEMA_VERSION = 1
_EVENTS_MIGRATIONS = {1: "scheduler_events_001.sql"}
_SENSITIVE_TERMS = (
    "password=",
    "token=",
    "api_key=",
    "api-key=",
    "access_key=",
    "access-key=",
    "bearer ",
    "-----begin ",
)


class SchedulerEventConflict(RuntimeError):
    """Raised when an event/trigger identity is reused with conflicting content."""


@dataclass(frozen=True, slots=True)
class SchedulerEventRecord:
    workspace_id: WorkspaceId
    id: SchedulerEventId
    event_type: str
    source_ref: str | None
    subject_ref: str | None
    payload_digest: str
    occurred_at: Instant
    received_at: Instant

    def __post_init__(self) -> None:
        if not self.event_type or self.event_type != self.event_type.strip():
            raise ValueError("scheduler event type must be non-empty and trimmed")
        if len(self.payload_digest) != 64 or any(
            char not in "0123456789abcdef" for char in self.payload_digest
        ):
            raise ValueError("scheduler event payload_digest must be lowercase sha256 hex")
        for name, value in (("source_ref", self.source_ref), ("subject_ref", self.subject_ref)):
            if value is None:
                continue
            if not value or value != value.strip() or "\n" in value or "\r" in value:
                raise ValueError(f"scheduler event {name} is invalid")
            folded = value.casefold()
            if any(term in folded for term in _SENSITIVE_TERMS):
                raise ValueError(f"scheduler event {name} must not contain credential material")


@dataclass(frozen=True, slots=True)
class EventDelivery:
    workspace_id: WorkspaceId
    event_id: SchedulerEventId
    trigger: EventTriggerDefinition
    workflow_run_id: WorkflowRunId | None = None
    state: str = "pending"

    def __post_init__(self) -> None:
        if self.state not in {"pending", "delivered"}:
            raise ValueError("event delivery state must be pending or delivered")
        if self.state == "pending" and self.workflow_run_id is not None:
            raise ValueError("pending event delivery cannot carry workflow_run_id")
        if self.state == "delivered" and self.workflow_run_id is None:
            raise ValueError("delivered event delivery requires workflow_run_id")


def _execute_script_in_transaction(connection: sqlite3.Connection, script: str) -> None:
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)


def migrate_scheduler_events(connection: sqlite3.Connection, *, now: Instant | str) -> None:
    now = Instant(now)
    migrate_scheduler_schedule(connection, now=now)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS scheduler_events_schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = connection.execute(
        "SELECT MAX(version) AS version FROM scheduler_events_schema_migrations"
    ).fetchone()
    current = 0 if row is None or row["version"] is None else int(row["version"])
    if current > _EVENTS_SCHEMA_VERSION:
        raise RuntimeError(
            f"scheduler events schema {current} is newer than supported {_EVENTS_SCHEMA_VERSION}"
        )
    migrations_dir = Path(__file__).with_name("migrations")
    for version in range(current + 1, _EVENTS_SCHEMA_VERSION + 1):
        script = migrations_dir.joinpath(_EVENTS_MIGRATIONS[version]).read_text(encoding="utf-8")
        connection.execute("BEGIN IMMEDIATE")
        try:
            _execute_script_in_transaction(connection, script)
            connection.execute(
                "INSERT INTO scheduler_events_schema_migrations(version,applied_at) VALUES (?,?)",
                (version, now),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def scheduler_events_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT MAX(version) AS version FROM scheduler_events_schema_migrations"
    ).fetchone()
    return 0 if row is None or row["version"] is None else int(row["version"])


def _event_from_row(row: sqlite3.Row) -> SchedulerEventRecord:
    return SchedulerEventRecord(
        WorkspaceId(row["workspace_id"]),
        SchedulerEventId(row["event_id"]),
        row["event_type"],
        row["source_ref"],
        row["subject_ref"],
        row["payload_digest"],
        Instant(row["occurred_at"]),
        Instant(row["received_at"]),
    )


def _delivery_from_row(row: sqlite3.Row) -> EventDelivery:
    run_id = row["workflow_run_id"]
    return EventDelivery(
        WorkspaceId(row["workspace_id"]),
        SchedulerEventId(row["event_id"]),
        EventTriggerDefinition.from_json(row["trigger_snapshot_json"]),
        None if run_id is None else WorkflowRunId(run_id),
        row["state"],
    )


def _event_run_id(
    workspace_id: WorkspaceId,
    event_id: SchedulerEventId,
    trigger_id: EventTriggerId,
) -> WorkflowRunId:
    digest = hashlib.sha256(
        encode_canonical_json(
            {
                "workspace_id": str(workspace_id),
                "event_id": str(event_id),
                "event_trigger_id": str(trigger_id),
            }
        )
    ).hexdigest()
    return WorkflowRunId(f"workflow-run-event-{digest[:32]}")


class SchedulerEventStore(SchedulerScheduleStore):
    """Reference SQLite event trigger/inbox/delivery store."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        super().__init__(path, migration_now=migration_now)
        connection = open_database(path)
        try:
            migrate_scheduler_events(connection, now=migration_now)
        finally:
            connection.close()

    def put_event_trigger(
        self,
        workspace_id: WorkspaceId,
        definition: EventTriggerDefinition,
        *,
        now: Instant | str,
    ) -> EventTriggerDefinition:
        current = Instant(now)
        payload = definition.to_json()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            workflow = connection.execute(
                "SELECT 1 FROM workflows WHERE workspace_id=? AND workflow_id=?",
                (str(workspace_id), str(definition.workflow_id)),
            ).fetchone()
            if workflow is None:
                raise SchedulerEventConflict("event trigger workflow does not exist")
            existing = connection.execute(
                "SELECT definition_json FROM event_triggers "
                "WHERE workspace_id=? AND event_trigger_id=?",
                (str(workspace_id), str(definition.id)),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO event_triggers("
                    "workspace_id,event_trigger_id,workflow_id,definition_json,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        str(workspace_id),
                        str(definition.id),
                        str(definition.workflow_id),
                        payload,
                        current,
                        current,
                    ),
                )
            elif existing["definition_json"] != payload:
                connection.execute(
                    "UPDATE event_triggers SET workflow_id=?,definition_json=?,updated_at=?,"
                    "row_version=row_version+1 WHERE workspace_id=? AND event_trigger_id=?",
                    (
                        str(definition.workflow_id),
                        payload,
                        current,
                        str(workspace_id),
                        str(definition.id),
                    ),
                )
            connection.execute("COMMIT")
            return definition
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def list_event_triggers(self, workspace_id: WorkspaceId) -> tuple[EventTriggerDefinition, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT definition_json FROM event_triggers "
                "WHERE workspace_id=? ORDER BY event_trigger_id",
                (str(workspace_id),),
            ).fetchall()
            return tuple(EventTriggerDefinition.from_json(row["definition_json"]) for row in rows)
        finally:
            connection.close()

    def ingest_event(
        self,
        event: SchedulerEventRecord,
    ) -> tuple[EventDelivery, ...]:
        """Persist one event and freeze its matching trigger snapshots exactly once."""

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, event.workspace_id)
            existing = connection.execute(
                "SELECT * FROM scheduler_events WHERE workspace_id=? AND event_id=?",
                (str(event.workspace_id), str(event.id)),
            ).fetchone()
            if existing is not None:
                if _event_from_row(existing) != event:
                    raise SchedulerEventConflict("scheduler event id has conflicting content")
                rows = connection.execute(
                    "SELECT * FROM scheduler_event_deliveries "
                    "WHERE workspace_id=? AND event_id=? ORDER BY event_trigger_id",
                    (str(event.workspace_id), str(event.id)),
                ).fetchall()
                connection.execute("COMMIT")
                return tuple(_delivery_from_row(row) for row in rows)

            connection.execute(
                "INSERT INTO scheduler_events("
                "workspace_id,event_id,event_type,source_ref,subject_ref,payload_digest,"
                "occurred_at,received_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    str(event.workspace_id),
                    str(event.id),
                    event.event_type,
                    event.source_ref,
                    event.subject_ref,
                    event.payload_digest,
                    event.occurred_at,
                    event.received_at,
                ),
            )
            trigger_rows = connection.execute(
                "SELECT definition_json FROM event_triggers WHERE workspace_id=? "
                "ORDER BY event_trigger_id",
                (str(event.workspace_id),),
            ).fetchall()
            deliveries: list[EventDelivery] = []
            for row in trigger_rows:
                definition = EventTriggerDefinition.from_json(row["definition_json"])
                if not definition.matches(
                    event_type=event.event_type,
                    source_ref=event.source_ref,
                    subject_ref=event.subject_ref,
                ):
                    continue
                connection.execute(
                    "INSERT INTO scheduler_event_deliveries("
                    "workspace_id,event_id,event_trigger_id,workflow_id,trigger_snapshot_json,"
                    "workflow_run_id,state,created_at,updated_at) VALUES (?,?,?,?,?,NULL,'pending',?,?)",
                    (
                        str(event.workspace_id),
                        str(event.id),
                        str(definition.id),
                        str(definition.workflow_id),
                        definition.to_json(),
                        event.received_at,
                        event.received_at,
                    ),
                )
                deliveries.append(EventDelivery(event.workspace_id, event.id, definition))
            connection.execute("COMMIT")
            return tuple(deliveries)
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_event(
        self,
        workspace_id: WorkspaceId,
        event_id: SchedulerEventId,
    ) -> SchedulerEventRecord | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM scheduler_events WHERE workspace_id=? AND event_id=?",
                (str(workspace_id), str(event_id)),
            ).fetchone()
            return None if row is None else _event_from_row(row)
        finally:
            connection.close()

    def list_pending_deliveries(
        self,
        workspace_id: WorkspaceId,
        *,
        limit: int = 100,
    ) -> tuple[EventDelivery, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("event delivery limit must be between 1 and 1000")
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM scheduler_event_deliveries "
                "WHERE workspace_id=? AND state='pending' "
                "ORDER BY created_at,event_id,event_trigger_id LIMIT ?",
                (str(workspace_id), limit),
            ).fetchall()
            return tuple(_delivery_from_row(row) for row in rows)
        finally:
            connection.close()

    def deliver_event(
        self,
        delivery: EventDelivery,
        *,
        now: Instant | str,
    ) -> EventDelivery:
        if delivery.state != "pending" or delivery.workflow_run_id is not None:
            raise ValueError("only pending event deliveries can be delivered")
        event = self.get_event(delivery.workspace_id, delivery.event_id)
        if event is None:
            raise KeyError(str(delivery.event_id))
        trigger = Trigger(
            "event",
            f"event:{delivery.event_id}:{delivery.trigger.id}",
            source_ref=event.source_ref or f"event-type:{event.event_type}",
        )
        run = self.create_run(
            delivery.workspace_id,
            _event_run_id(delivery.workspace_id, delivery.event_id, delivery.trigger.id),
            delivery.trigger.workflow_id,
            trigger,
            now=now,
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM scheduler_event_deliveries "
                "WHERE workspace_id=? AND event_id=? AND event_trigger_id=?",
                (
                    str(delivery.workspace_id),
                    str(delivery.event_id),
                    str(delivery.trigger.id),
                ),
            ).fetchone()
            if row is None:
                raise KeyError(str(delivery.trigger.id))
            if row["state"] == "delivered":
                existing = _delivery_from_row(row)
                if existing.workflow_run_id != run.id:
                    raise SchedulerEventConflict(
                        "event delivery maps to conflicting workflow run"
                    )
                connection.execute("COMMIT")
                return existing
            connection.execute(
                "UPDATE scheduler_event_deliveries SET state='delivered',workflow_run_id=?,"
                "updated_at=? WHERE workspace_id=? AND event_id=? AND event_trigger_id=?",
                (
                    str(run.id),
                    Instant(now),
                    str(delivery.workspace_id),
                    str(delivery.event_id),
                    str(delivery.trigger.id),
                ),
            )
            connection.execute("COMMIT")
            return EventDelivery(
                delivery.workspace_id,
                delivery.event_id,
                delivery.trigger,
                run.id,
                "delivered",
            )
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()


__all__ = (
    "EventDelivery",
    "SchedulerEventConflict",
    "SchedulerEventRecord",
    "SchedulerEventStore",
    "migrate_scheduler_events",
    "scheduler_events_schema_version",
)
