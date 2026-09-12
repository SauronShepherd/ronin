"""Durable scheduler backfill requests and deterministic backfill-run mapping."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path

from studio_core import ScheduleId, Trigger, WorkflowRunId, WorkspaceId
from studio_core.canonical_json import encode as encode_canonical_json
from studio_orchestrator import Instant

from .scheduler_events import SchedulerEventStore, migrate_scheduler_events
from .sqlite import open_database

_BACKFILL_SCHEMA_VERSION = 1
_BACKFILL_MIGRATIONS = {1: "scheduler_backfill_001.sql"}


class BackfillConflict(RuntimeError):
    """Raised when backfill identity/state conflicts with a requested mutation."""


@dataclass(frozen=True, order=True, slots=True)
class BackfillId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or self.value != self.value.strip() or "\n" in self.value:
            raise ValueError("backfill id must be non-empty, trimmed, and single-line")
        if len(self.value) > 256:
            raise ValueError("backfill id must be at most 256 characters")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class BackfillRequest:
    id: BackfillId
    schedule_id: ScheduleId
    start_at: Instant
    end_at: Instant
    state: str = "pending"

    def __post_init__(self) -> None:
        if self.state not in {"pending", "running", "completed", "cancelled"}:
            raise ValueError("invalid backfill state")
        if not _minute_aligned(self.start_at) or not _minute_aligned(self.end_at):
            raise ValueError("backfill range must be aligned to UTC minutes")
        if self.end_at < self.start_at:
            raise ValueError("backfill end_at must not precede start_at")


@dataclass(frozen=True, slots=True)
class BackfillRun:
    workspace_id: WorkspaceId
    backfill_id: BackfillId
    logical_time: Instant
    workflow_run_id: WorkflowRunId


def _minute_aligned(value: Instant) -> bool:
    return str(value)[17:26] == "00.000000"


def _execute_script_in_transaction(connection: sqlite3.Connection, script: str) -> None:
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)


def migrate_scheduler_backfill(connection: sqlite3.Connection, *, now: Instant | str) -> None:
    now = Instant(now)
    migrate_scheduler_events(connection, now=now)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS scheduler_backfill_schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = connection.execute(
        "SELECT MAX(version) AS version FROM scheduler_backfill_schema_migrations"
    ).fetchone()
    current = 0 if row is None or row["version"] is None else int(row["version"])
    if current > _BACKFILL_SCHEMA_VERSION:
        raise RuntimeError(
            f"scheduler backfill schema {current} is newer than supported {_BACKFILL_SCHEMA_VERSION}"
        )
    migrations_dir = Path(__file__).with_name("migrations")
    for version in range(current + 1, _BACKFILL_SCHEMA_VERSION + 1):
        script = migrations_dir.joinpath(_BACKFILL_MIGRATIONS[version]).read_text(
            encoding="utf-8"
        )
        connection.execute("BEGIN IMMEDIATE")
        try:
            _execute_script_in_transaction(connection, script)
            connection.execute(
                "INSERT INTO scheduler_backfill_schema_migrations(version,applied_at) VALUES (?,?)",
                (version, now),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def scheduler_backfill_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT MAX(version) AS version FROM scheduler_backfill_schema_migrations"
    ).fetchone()
    return 0 if row is None or row["version"] is None else int(row["version"])


def _request_from_row(row: sqlite3.Row) -> BackfillRequest:
    return BackfillRequest(
        BackfillId(row["backfill_id"]),
        ScheduleId(row["schedule_id"]),
        Instant(row["start_at"]),
        Instant(row["end_at"]),
        row["state"],
    )


def _backfill_run_id(
    workspace_id: WorkspaceId,
    backfill_id: BackfillId,
    logical_time: Instant,
) -> WorkflowRunId:
    digest = hashlib.sha256(
        encode_canonical_json(
            {
                "workspace_id": str(workspace_id),
                "backfill_id": str(backfill_id),
                "logical_time": str(logical_time),
            }
        )
    ).hexdigest()
    return WorkflowRunId(f"workflow-run-backfill-{digest[:32]}")


class SchedulerBackfillStore(SchedulerEventStore):
    """Reference SQLite backfill store layered over existing scheduler semantics."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        super().__init__(path, migration_now=migration_now)
        connection = open_database(path)
        try:
            migrate_scheduler_backfill(connection, now=migration_now)
        finally:
            connection.close()

    def create_backfill(
        self,
        workspace_id: WorkspaceId,
        request: BackfillRequest,
        *,
        now: Instant | str,
    ) -> BackfillRequest:
        if request.state != "pending":
            raise ValueError("new backfill requests must start pending")
        current = Instant(now)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            schedule = connection.execute(
                "SELECT 1 FROM schedules WHERE workspace_id=? AND schedule_id=?",
                (str(workspace_id), str(request.schedule_id)),
            ).fetchone()
            if schedule is None:
                raise BackfillConflict("backfill schedule does not exist")
            existing = connection.execute(
                "SELECT * FROM scheduler_backfills WHERE workspace_id=? AND backfill_id=?",
                (str(workspace_id), str(request.id)),
            ).fetchone()
            if existing is not None:
                found = _request_from_row(existing)
                if found != request:
                    raise BackfillConflict("backfill id already exists with different content")
                connection.execute("COMMIT")
                return found
            connection.execute(
                "INSERT INTO scheduler_backfills("
                "workspace_id,backfill_id,schedule_id,start_at,end_at,state,created_at,updated_at) "
                "VALUES (?,?,?,?,?,'pending',?,?)",
                (
                    str(workspace_id),
                    str(request.id),
                    str(request.schedule_id),
                    request.start_at,
                    request.end_at,
                    current,
                    current,
                ),
            )
            connection.execute("COMMIT")
            return request
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_backfill(
        self,
        workspace_id: WorkspaceId,
        backfill_id: BackfillId,
    ) -> BackfillRequest | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM scheduler_backfills WHERE workspace_id=? AND backfill_id=?",
                (str(workspace_id), str(backfill_id)),
            ).fetchone()
            return None if row is None else _request_from_row(row)
        finally:
            connection.close()

    def cancel_backfill(
        self,
        workspace_id: WorkspaceId,
        backfill_id: BackfillId,
        *,
        now: Instant | str,
    ) -> BackfillRequest:
        current = Instant(now)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM scheduler_backfills WHERE workspace_id=? AND backfill_id=?",
                (str(workspace_id), str(backfill_id)),
            ).fetchone()
            if row is None:
                raise KeyError(str(backfill_id))
            request = _request_from_row(row)
            if request.state == "completed":
                raise BackfillConflict("completed backfill cannot be cancelled")
            if request.state != "cancelled":
                connection.execute(
                    "UPDATE scheduler_backfills SET state='cancelled',updated_at=?,"
                    "row_version=row_version+1 WHERE workspace_id=? AND backfill_id=?",
                    (current, str(workspace_id), str(backfill_id)),
                )
                request = replace(request, state="cancelled")
            connection.execute("COMMIT")
            return request
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def create_backfill_run(
        self,
        workspace_id: WorkspaceId,
        backfill_id: BackfillId,
        *,
        logical_time: Instant | str,
        now: Instant | str,
    ) -> BackfillRun:
        logical = Instant(logical_time)
        if not _minute_aligned(logical):
            raise ValueError("backfill logical_time must be aligned to a UTC minute")
        request = self.get_backfill(workspace_id, backfill_id)
        if request is None:
            raise KeyError(str(backfill_id))
        if request.state in {"completed", "cancelled"}:
            raise BackfillConflict(f"cannot create run for {request.state} backfill")
        if not request.start_at <= logical <= request.end_at:
            raise ValueError("backfill logical_time is outside requested range")
        schedule = self.get_schedule(workspace_id, request.schedule_id)
        if schedule is None:
            raise BackfillConflict("backfill schedule no longer exists")
        trigger = Trigger(
            "backfill",
            f"backfill:{backfill_id}:{logical}",
            source_ref=f"schedule:{request.schedule_id}",
        )
        run = self.create_run(
            workspace_id,
            _backfill_run_id(workspace_id, backfill_id, logical),
            schedule.workflow_id,
            trigger,
            now=now,
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current_row = connection.execute(
                "SELECT state FROM scheduler_backfills WHERE workspace_id=? AND backfill_id=?",
                (str(workspace_id), str(backfill_id)),
            ).fetchone()
            if current_row is None:
                raise KeyError(str(backfill_id))
            if current_row["state"] == "cancelled":
                raise BackfillConflict("backfill was cancelled before run commit")
            existing = connection.execute(
                "SELECT workflow_run_id FROM scheduler_backfill_runs "
                "WHERE workspace_id=? AND backfill_id=? AND logical_time=?",
                (str(workspace_id), str(backfill_id), logical),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO scheduler_backfill_runs("
                    "workspace_id,backfill_id,logical_time,workflow_run_id,created_at) "
                    "VALUES (?,?,?,?,?)",
                    (str(workspace_id), str(backfill_id), logical, str(run.id), Instant(now)),
                )
            elif existing["workflow_run_id"] != str(run.id):
                raise BackfillConflict("backfill logical time maps to conflicting workflow run")
            if current_row["state"] == "pending":
                connection.execute(
                    "UPDATE scheduler_backfills SET state='running',updated_at=?,"
                    "row_version=row_version+1 WHERE workspace_id=? AND backfill_id=?",
                    (Instant(now), str(workspace_id), str(backfill_id)),
                )
            connection.execute("COMMIT")
            return BackfillRun(workspace_id, backfill_id, logical, run.id)
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def complete_backfill(
        self,
        workspace_id: WorkspaceId,
        backfill_id: BackfillId,
        *,
        now: Instant | str,
    ) -> BackfillRequest:
        current = Instant(now)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM scheduler_backfills WHERE workspace_id=? AND backfill_id=?",
                (str(workspace_id), str(backfill_id)),
            ).fetchone()
            if row is None:
                raise KeyError(str(backfill_id))
            request = _request_from_row(row)
            if request.state == "cancelled":
                raise BackfillConflict("cancelled backfill cannot be completed")
            if request.state != "completed":
                connection.execute(
                    "UPDATE scheduler_backfills SET state='completed',updated_at=?,"
                    "row_version=row_version+1 WHERE workspace_id=? AND backfill_id=?",
                    (current, str(workspace_id), str(backfill_id)),
                )
                request = replace(request, state="completed")
            connection.execute("COMMIT")
            return request
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def list_backfill_runs(
        self,
        workspace_id: WorkspaceId,
        backfill_id: BackfillId,
    ) -> tuple[BackfillRun, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT logical_time,workflow_run_id FROM scheduler_backfill_runs "
                "WHERE workspace_id=? AND backfill_id=? ORDER BY logical_time",
                (str(workspace_id), str(backfill_id)),
            ).fetchall()
            return tuple(
                BackfillRun(
                    workspace_id,
                    backfill_id,
                    Instant(row["logical_time"]),
                    WorkflowRunId(row["workflow_run_id"]),
                )
                for row in rows
            )
        finally:
            connection.close()


__all__ = (
    "BackfillConflict",
    "BackfillId",
    "BackfillRequest",
    "BackfillRun",
    "SchedulerBackfillStore",
    "migrate_scheduler_backfill",
    "scheduler_backfill_schema_version",
)
