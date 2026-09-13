"""Snapshot-safe scheduler backfill generation and concurrency state."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from studio_core import (
    Schedule,
    Trigger,
    WorkflowDefinition,
    WorkflowRun,
    WorkspaceId,
)
from studio_orchestrator import Instant

from .scheduler import _task_run_id
from .scheduler_backfill import (
    BackfillConflict,
    BackfillId,
    BackfillRequest,
    BackfillRun,
    SchedulerBackfillStore,
    _backfill_run_id,
    _run_from_row,
    migrate_scheduler_backfill,
)
from .sqlite import open_database

_BACKFILL_RUNTIME_SCHEMA_VERSION = 1
_BACKFILL_RUNTIME_MIGRATIONS = {1: "scheduler_backfill_runtime_001.sql"}


class BackfillCapacityExhausted(RuntimeError):
    """Raised when a backfill has reached its durable active-run cap."""


@dataclass(frozen=True, slots=True)
class BackfillPlan:
    request: BackfillRequest
    schedule_snapshot: Schedule
    workflow_snapshot: WorkflowDefinition
    cursor_at: Instant | None
    max_concurrency: int
    generation_complete: bool


def _execute_script_in_transaction(connection: sqlite3.Connection, script: str) -> None:
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)


def migrate_scheduler_backfill_runtime(
    connection: sqlite3.Connection,
    *,
    now: Instant | str,
) -> None:
    current_time = Instant(now)
    migrate_scheduler_backfill(connection, now=current_time)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS scheduler_backfill_runtime_schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = connection.execute(
        "SELECT MAX(version) AS version FROM scheduler_backfill_runtime_schema_migrations"
    ).fetchone()
    current = 0 if row is None or row["version"] is None else int(row["version"])
    if current > _BACKFILL_RUNTIME_SCHEMA_VERSION:
        raise RuntimeError(
            f"scheduler backfill runtime schema {current} is newer than supported "
            f"{_BACKFILL_RUNTIME_SCHEMA_VERSION}"
        )
    migrations_dir = Path(__file__).with_name("migrations")
    for version in range(current + 1, _BACKFILL_RUNTIME_SCHEMA_VERSION + 1):
        script = migrations_dir.joinpath(_BACKFILL_RUNTIME_MIGRATIONS[version]).read_text(
            encoding="utf-8"
        )
        connection.execute("BEGIN IMMEDIATE")
        try:
            _execute_script_in_transaction(connection, script)
            connection.execute(
                "INSERT INTO scheduler_backfill_runtime_schema_migrations(version,applied_at) "
                "VALUES (?,?)",
                (version, current_time),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def scheduler_backfill_runtime_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT MAX(version) AS version FROM scheduler_backfill_runtime_schema_migrations"
    ).fetchone()
    return 0 if row is None or row["version"] is None else int(row["version"])


class SchedulerBackfillRuntimeStore(SchedulerBackfillStore):
    """Backfill store with immutable snapshots, cursoring, and active-run bounds."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        super().__init__(path, migration_now=migration_now)
        connection = open_database(path)
        try:
            migrate_scheduler_backfill_runtime(connection, now=migration_now)
        finally:
            connection.close()

    def create_backfill_plan(
        self,
        workspace_id: WorkspaceId,
        request: BackfillRequest,
        *,
        max_concurrency: int,
        now: Instant | str,
    ) -> BackfillPlan:
        if max_concurrency < 1:
            raise ValueError("backfill max_concurrency must be positive")
        existing = self.get_backfill_plan(workspace_id, request.id)
        if existing is not None:
            same_identity = (
                existing.request.id == request.id
                and existing.request.schedule_id == request.schedule_id
                and existing.request.start_at == request.start_at
                and existing.request.end_at == request.end_at
                and existing.max_concurrency == max_concurrency
            )
            if not same_identity:
                raise BackfillConflict("backfill plan already exists with different content")
            return existing

        schedule = self.get_schedule(workspace_id, request.schedule_id)
        if schedule is None:
            raise BackfillConflict("backfill schedule does not exist")
        workflow = self.get_workflow(workspace_id, schedule.workflow_id)
        if workflow is None:
            raise BackfillConflict("backfill workflow does not exist")
        self.create_backfill(workspace_id, request, now=now)

        current = Instant(now)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            connection.execute(
                "INSERT INTO scheduler_backfill_plans("
                "workspace_id,backfill_id,schedule_json,workflow_json,cursor_at,"
                "max_concurrency,generation_complete,created_at,updated_at) "
                "VALUES (?,?,?,?,NULL,?,0,?,?)",
                (
                    str(workspace_id),
                    str(request.id),
                    schedule.to_json(),
                    workflow.to_json(),
                    max_concurrency,
                    current,
                    current,
                ),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        return BackfillPlan(request, schedule, workflow, None, max_concurrency, False)

    def get_backfill_plan(
        self,
        workspace_id: WorkspaceId,
        backfill_id: BackfillId,
    ) -> BackfillPlan | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT b.*,p.schedule_json,p.workflow_json,p.cursor_at,"
                "p.max_concurrency,p.generation_complete "
                "FROM scheduler_backfills b JOIN scheduler_backfill_plans p "
                "ON p.workspace_id=b.workspace_id AND p.backfill_id=b.backfill_id "
                "WHERE b.workspace_id=? AND b.backfill_id=?",
                (str(workspace_id), str(backfill_id)),
            ).fetchone()
            if row is None:
                return None
            schedule = Schedule.from_json(row["schedule_json"])
            request = BackfillRequest(
                BackfillId(row["backfill_id"]),
                schedule_id=schedule.id,
                start_at=Instant(row["start_at"]),
                end_at=Instant(row["end_at"]),
                state=row["state"],
            )
            return BackfillPlan(
                request,
                schedule,
                WorkflowDefinition.from_json(row["workflow_json"]),
                None if row["cursor_at"] is None else Instant(row["cursor_at"]),
                int(row["max_concurrency"]),
                bool(row["generation_complete"]),
            )
        finally:
            connection.close()

    def count_active_backfill_runs(
        self,
        workspace_id: WorkspaceId,
        backfill_id: BackfillId,
    ) -> int:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM scheduler_backfill_runs r "
                "LEFT JOIN workflow_runs w ON w.workspace_id=r.workspace_id "
                "AND w.workflow_run_id=r.workflow_run_id "
                "WHERE r.workspace_id=? AND r.backfill_id=? "
                "AND (r.state='reserved' OR w.state IN ('pending','running','cancelling'))",
                (str(workspace_id), str(backfill_id)),
            ).fetchone()
            if row is None:
                raise AssertionError("backfill active-run query returned no row")
            return int(row["count"])
        finally:
            connection.close()

    def advance_backfill_cursor(
        self,
        workspace_id: WorkspaceId,
        backfill_id: BackfillId,
        *,
        through: Instant | str,
        generation_complete: bool,
        now: Instant | str,
    ) -> BackfillPlan:
        logical = Instant(through)
        current = Instant(now)
        plan = self.get_backfill_plan(workspace_id, backfill_id)
        if plan is None:
            raise KeyError(str(backfill_id))
        if logical < plan.request.start_at or logical > plan.request.end_at:
            raise ValueError("backfill cursor must remain inside requested range")
        if plan.cursor_at is not None and logical < plan.cursor_at:
            raise ValueError("backfill cursor must not move backwards")
        if generation_complete and logical != plan.request.end_at:
            raise ValueError("backfill generation can complete only at end_at")

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            connection.execute(
                "UPDATE scheduler_backfill_plans SET cursor_at=?,generation_complete=?,"
                "updated_at=? WHERE workspace_id=? AND backfill_id=?",
                (
                    logical,
                    1 if generation_complete else 0,
                    current,
                    str(workspace_id),
                    str(backfill_id),
                ),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        updated = self.get_backfill_plan(workspace_id, backfill_id)
        if updated is None:
            raise AssertionError("backfill plan disappeared after cursor update")
        return updated

    def _reserve_snapshot_backfill_run(
        self,
        workspace_id: WorkspaceId,
        backfill_id: BackfillId,
        logical: Instant,
        *,
        now: Instant,
    ) -> BackfillRun:
        """Reserve one logical run while atomically enforcing backfill capacity."""

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            row = connection.execute(
                "SELECT b.*,p.max_concurrency,p.schedule_json FROM scheduler_backfills b "
                "JOIN scheduler_backfill_plans p ON p.workspace_id=b.workspace_id "
                "AND p.backfill_id=b.backfill_id "
                "WHERE b.workspace_id=? AND b.backfill_id=?",
                (str(workspace_id), str(backfill_id)),
            ).fetchone()
            if row is None:
                raise KeyError(str(backfill_id))
            request = BackfillRequest(
                BackfillId(row["backfill_id"]),
                schedule_id=Schedule.from_json(row["schedule_json"]).id,
                start_at=Instant(row["start_at"]),
                end_at=Instant(row["end_at"]),
                state=row["state"],
            )
            if request.state in {"completed", "cancelled"}:
                raise BackfillConflict(f"cannot reserve run for {request.state} backfill")
            if not request.start_at <= logical <= request.end_at:
                raise ValueError("backfill logical_time is outside requested range")

            run_id = _backfill_run_id(workspace_id, backfill_id, logical)
            existing = connection.execute(
                "SELECT * FROM scheduler_backfill_runs "
                "WHERE workspace_id=? AND backfill_id=? AND logical_time=?",
                (str(workspace_id), str(backfill_id), logical),
            ).fetchone()
            if existing is not None:
                reserved = _run_from_row(workspace_id, existing)
                if reserved.workflow_run_id != run_id:
                    raise BackfillConflict(
                        "backfill logical time maps to conflicting workflow run"
                    )
                connection.execute("COMMIT")
                return reserved

            active = connection.execute(
                "SELECT COUNT(*) AS count FROM scheduler_backfill_runs r "
                "LEFT JOIN workflow_runs w ON w.workspace_id=r.workspace_id "
                "AND w.workflow_run_id=r.workflow_run_id "
                "WHERE r.workspace_id=? AND r.backfill_id=? "
                "AND (r.state='reserved' OR w.state IN ('pending','running','cancelling'))",
                (str(workspace_id), str(backfill_id)),
            ).fetchone()
            if active is None:
                raise AssertionError("backfill active-run query returned no row")
            if int(active["count"]) >= int(row["max_concurrency"]):
                raise BackfillCapacityExhausted(str(backfill_id))

            connection.execute(
                "INSERT INTO scheduler_backfill_runs("
                "workspace_id,backfill_id,logical_time,workflow_run_id,state,created_at,updated_at) "
                "VALUES (?,?,?,?,'reserved',?,?)",
                (
                    str(workspace_id),
                    str(backfill_id),
                    logical,
                    str(run_id),
                    now,
                    now,
                ),
            )
            if request.state == "pending":
                connection.execute(
                    "UPDATE scheduler_backfills SET state='running',updated_at=?,"
                    "row_version=row_version+1 WHERE workspace_id=? AND backfill_id=?",
                    (now, str(workspace_id), str(backfill_id)),
                )
            connection.execute("COMMIT")
            return BackfillRun(workspace_id, backfill_id, logical, run_id, "reserved")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def create_snapshot_backfill_run(
        self,
        workspace_id: WorkspaceId,
        backfill_id: BackfillId,
        *,
        logical_time: Instant | str,
        now: Instant | str,
    ) -> BackfillRun:
        plan = self.get_backfill_plan(workspace_id, backfill_id)
        if plan is None:
            raise KeyError(str(backfill_id))
        logical = Instant(logical_time)
        current = Instant(now)
        reserved = self._reserve_snapshot_backfill_run(
            workspace_id,
            backfill_id,
            logical,
            now=current,
        )
        if reserved.state == "created":
            return reserved

        trigger = Trigger(
            "backfill",
            f"backfill:{backfill_id}:{logical}",
            source_ref=f"schedule:{plan.schedule_snapshot.id}",
        )
        run = WorkflowRun(
            reserved.workflow_run_id,
            plan.workflow_snapshot.id,
            plan.workflow_snapshot,
            trigger,
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            existing = connection.execute(
                "SELECT run_json FROM workflow_runs WHERE workspace_id=? AND workflow_run_id=?",
                (str(workspace_id), str(run.id)),
            ).fetchone()
            if existing is None:
                trigger_conflict = connection.execute(
                    "SELECT workflow_run_id FROM workflow_runs WHERE workspace_id=? "
                    "AND workflow_id=? AND trigger_key=?",
                    (str(workspace_id), str(run.workflow_id), trigger.key),
                ).fetchone()
                if trigger_conflict is not None:
                    raise BackfillConflict("backfill trigger key maps to conflicting workflow run")
                connection.execute(
                    "INSERT INTO workflow_runs("
                    "workspace_id,workflow_run_id,workflow_id,trigger_key,state,run_json,"
                    "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        str(workspace_id),
                        str(run.id),
                        str(run.workflow_id),
                        trigger.key,
                        run.state,
                        run.to_json(),
                        current,
                        current,
                    ),
                )
                for node in plan.workflow_snapshot.pipeline.nodes:
                    task_id = _task_run_id(run.id, node.id.value)
                    connection.execute(
                        "INSERT INTO task_runs("
                        "workspace_id,task_run_id,workflow_run_id,node_id,state,attempt_count,"
                        "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                        (
                            str(workspace_id),
                            str(task_id),
                            str(run.id),
                            node.id.value,
                            "pending",
                            0,
                            current,
                            current,
                        ),
                    )
            elif WorkflowRun.from_json(existing["run_json"]) != run:
                raise BackfillConflict("backfill workflow run identity has conflicting content")

            connection.execute(
                "UPDATE scheduler_backfill_runs SET state='created',updated_at=? "
                "WHERE workspace_id=? AND backfill_id=? AND logical_time=?",
                (current, str(workspace_id), str(backfill_id), logical),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        return BackfillRun(workspace_id, backfill_id, logical, run.id, "created")


__all__ = (
    "BackfillCapacityExhausted",
    "BackfillPlan",
    "SchedulerBackfillRuntimeStore",
    "migrate_scheduler_backfill_runtime",
    "scheduler_backfill_runtime_schema_version",
)
