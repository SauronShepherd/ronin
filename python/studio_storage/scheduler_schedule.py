"""Durable schedule evaluation cursors and idempotent fire ledger."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from studio_core import Schedule, ScheduleId, Trigger, WorkflowRunId, WorkspaceId
from studio_core.canonical_json import encode as encode_canonical_json
from studio_orchestrator import Instant

from .scheduler_controller import SchedulerControllerStore, migrate_scheduler_controller
from .sqlite import open_database

_SCHEDULE_SCHEMA_VERSION = 1
_SCHEDULE_MIGRATIONS = {1: "scheduler_schedule_001.sql"}


class ScheduleFireConflict(RuntimeError):
    """Raised when one logical schedule fire conflicts with durable state."""


@dataclass(frozen=True, slots=True)
class ScheduleFire:
    workspace_id: WorkspaceId
    schedule_id: ScheduleId
    scheduled_for: Instant
    workflow_run_id: WorkflowRunId


def _execute_script_in_transaction(connection: sqlite3.Connection, script: str) -> None:
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)


def migrate_scheduler_schedule(connection: sqlite3.Connection, *, now: Instant | str) -> None:
    now = Instant(now)
    migrate_scheduler_controller(connection, now=now)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS scheduler_schedule_schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = connection.execute(
        "SELECT MAX(version) AS version FROM scheduler_schedule_schema_migrations"
    ).fetchone()
    current = 0 if row is None or row["version"] is None else int(row["version"])
    if current > _SCHEDULE_SCHEMA_VERSION:
        raise RuntimeError(
            f"scheduler schedule schema {current} is newer than supported "
            f"{_SCHEDULE_SCHEMA_VERSION}"
        )
    migrations_dir = Path(__file__).with_name("migrations")
    for version in range(current + 1, _SCHEDULE_SCHEMA_VERSION + 1):
        script = migrations_dir.joinpath(_SCHEDULE_MIGRATIONS[version]).read_text(
            encoding="utf-8"
        )
        connection.execute("BEGIN IMMEDIATE")
        try:
            _execute_script_in_transaction(connection, script)
            connection.execute(
                "INSERT INTO scheduler_schedule_schema_migrations(version,applied_at) "
                "VALUES (?,?)",
                (version, now),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def scheduler_schedule_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT MAX(version) AS version FROM scheduler_schedule_schema_migrations"
    ).fetchone()
    return 0 if row is None or row["version"] is None else int(row["version"])


def _minute_aligned(value: Instant) -> bool:
    return str(value)[17:26] == "00.000000"


def _schedule_run_id(
    workspace_id: WorkspaceId,
    schedule_id: ScheduleId,
    scheduled_for: Instant,
) -> WorkflowRunId:
    digest = hashlib.sha256(
        encode_canonical_json(
            {
                "workspace_id": str(workspace_id),
                "schedule_id": str(schedule_id),
                "scheduled_for": str(scheduled_for),
            }
        )
    ).hexdigest()
    return WorkflowRunId(f"workflow-run-schedule-{digest[:32]}")


class SchedulerScheduleStore(SchedulerControllerStore):
    """Reference SQLite scheduler store with durable cron evaluation state."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        super().__init__(path, migration_now=migration_now)
        connection = open_database(path)
        try:
            migrate_scheduler_schedule(connection, now=migration_now)
        finally:
            connection.close()

    def list_schedules(self, workspace_id: WorkspaceId) -> tuple[Schedule, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT schedule_json FROM schedules WHERE workspace_id=? ORDER BY schedule_id",
                (str(workspace_id),),
            ).fetchall()
            return tuple(Schedule.from_json(row["schedule_json"]) for row in rows)
        finally:
            connection.close()

    def get_schedule_cursor(
        self,
        workspace_id: WorkspaceId,
        schedule_id: ScheduleId,
    ) -> Instant | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT last_evaluated_at FROM schedule_cursors "
                "WHERE workspace_id=? AND schedule_id=?",
                (str(workspace_id), str(schedule_id)),
            ).fetchone()
            return None if row is None else Instant(row["last_evaluated_at"])
        finally:
            connection.close()

    def advance_schedule_cursor(
        self,
        workspace_id: WorkspaceId,
        schedule_id: ScheduleId,
        *,
        through: Instant | str,
        now: Instant | str,
    ) -> Instant:
        through_instant = Instant(through)
        current = Instant(now)
        if not _minute_aligned(through_instant):
            raise ValueError("schedule cursor must be aligned to a UTC minute")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            schedule = connection.execute(
                "SELECT 1 FROM schedules WHERE workspace_id=? AND schedule_id=?",
                (str(workspace_id), str(schedule_id)),
            ).fetchone()
            if schedule is None:
                raise KeyError(str(schedule_id))
            existing = connection.execute(
                "SELECT last_evaluated_at FROM schedule_cursors "
                "WHERE workspace_id=? AND schedule_id=?",
                (str(workspace_id), str(schedule_id)),
            ).fetchone()
            if existing is not None and Instant(existing["last_evaluated_at"]) > through_instant:
                raise ValueError("schedule cursor must not move backwards")
            connection.execute(
                "INSERT INTO schedule_cursors("
                "workspace_id,schedule_id,last_evaluated_at,updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT(workspace_id,schedule_id) DO UPDATE SET "
                "last_evaluated_at=excluded.last_evaluated_at,updated_at=excluded.updated_at",
                (str(workspace_id), str(schedule_id), through_instant, current),
            )
            connection.execute("COMMIT")
            return through_instant
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def fire_schedule(
        self,
        workspace_id: WorkspaceId,
        schedule_id: ScheduleId,
        *,
        scheduled_for: Instant | str,
        now: Instant | str,
    ) -> ScheduleFire:
        logical_time = Instant(scheduled_for)
        if not _minute_aligned(logical_time):
            raise ValueError("scheduled_for must be aligned to a UTC minute")
        schedule = self.get_schedule(workspace_id, schedule_id)
        if schedule is None:
            raise KeyError(str(schedule_id))
        if not schedule.enabled:
            raise ScheduleFireConflict("cannot fire a disabled schedule")
        trigger = Trigger(
            "schedule",
            f"schedule:{schedule.id}:{logical_time}",
            source_ref=f"schedule:{schedule.id}",
        )
        run = self.create_run(
            workspace_id,
            _schedule_run_id(workspace_id, schedule.id, logical_time),
            schedule.workflow_id,
            trigger,
            now=now,
        )
        fire = ScheduleFire(workspace_id, schedule.id, logical_time, run.id)

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT workflow_run_id FROM schedule_fires "
                "WHERE workspace_id=? AND schedule_id=? AND scheduled_for=?",
                (str(workspace_id), str(schedule.id), logical_time),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO schedule_fires("
                    "workspace_id,schedule_id,scheduled_for,workflow_run_id,created_at) "
                    "VALUES (?,?,?,?,?)",
                    (
                        str(workspace_id),
                        str(schedule.id),
                        logical_time,
                        str(run.id),
                        Instant(now),
                    ),
                )
            elif existing["workflow_run_id"] != str(run.id):
                raise ScheduleFireConflict("logical schedule fire maps to conflicting workflow run")
            connection.execute("COMMIT")
            return fire
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def list_schedule_fires(
        self,
        workspace_id: WorkspaceId,
        schedule_id: ScheduleId,
    ) -> tuple[ScheduleFire, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT scheduled_for,workflow_run_id FROM schedule_fires "
                "WHERE workspace_id=? AND schedule_id=? ORDER BY scheduled_for",
                (str(workspace_id), str(schedule_id)),
            ).fetchall()
            return tuple(
                ScheduleFire(
                    workspace_id,
                    schedule_id,
                    Instant(row["scheduled_for"]),
                    WorkflowRunId(row["workflow_run_id"]),
                )
                for row in rows
            )
        finally:
            connection.close()


__all__ = (
    "ScheduleFire",
    "ScheduleFireConflict",
    "SchedulerScheduleStore",
    "migrate_scheduler_schedule",
    "scheduler_schedule_schema_version",
)
