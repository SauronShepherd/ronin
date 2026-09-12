"""Durable workflow/schedule/run persistence before scheduler dispatch semantics are enabled."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import cast

from studio_core import (
    NodeId,
    Schedule,
    ScheduleId,
    TaskRun,
    TaskRunId,
    TaskRunState,
    Trigger,
    WorkflowDefinition,
    WorkflowId,
    WorkflowRun,
    WorkflowRunId,
    WorkspaceId,
)
from studio_core.canonical_json import encode as encode_canonical_json
from studio_orchestrator import Instant

from .sqlite import open_database
from .workspaces import WorkspaceNotFound, migrate_workspaces

_SCHEDULER_SCHEMA_VERSION = 1
_SCHEDULER_MIGRATIONS = {1: "scheduler_001.sql"}


class WorkflowConflict(RuntimeError):
    """Raised when workflow identity is reused with conflicting content."""


class WorkflowNotFound(KeyError):
    """Raised when a workflow definition does not exist."""


class WorkflowRunConflict(RuntimeError):
    """Raised when run/trigger identity conflicts with durable state."""


def _execute_script_in_transaction(connection: sqlite3.Connection, script: str) -> None:
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)


def migrate_scheduler(connection: sqlite3.Connection, *, now: Instant | str) -> None:
    now = Instant(now)
    migrate_workspaces(connection, now=now)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS scheduler_schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = connection.execute(
        "SELECT MAX(version) AS version FROM scheduler_schema_migrations"
    ).fetchone()
    current = 0 if row is None or row["version"] is None else int(row["version"])
    if current > _SCHEDULER_SCHEMA_VERSION:
        raise RuntimeError(
            f"scheduler schema {current} is newer than supported {_SCHEDULER_SCHEMA_VERSION}"
        )
    migrations_dir = Path(__file__).with_name("migrations")
    for version in range(current + 1, _SCHEDULER_SCHEMA_VERSION + 1):
        script = migrations_dir.joinpath(_SCHEDULER_MIGRATIONS[version]).read_text(encoding="utf-8")
        connection.execute("BEGIN IMMEDIATE")
        try:
            _execute_script_in_transaction(connection, script)
            connection.execute(
                "INSERT INTO scheduler_schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, now),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def scheduler_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT MAX(version) AS version FROM scheduler_schema_migrations"
    ).fetchone()
    return 0 if row is None or row["version"] is None else int(row["version"])


def _task_run_id(run_id: WorkflowRunId, node_id: str) -> TaskRunId:
    digest = hashlib.sha256(
        encode_canonical_json({"workflow_run_id": run_id.value, "node_id": node_id})
    ).hexdigest()
    return TaskRunId(f"task-{digest[:32]}")


class SqliteSchedulerStore:
    """SQLite definition/run snapshot store; task claiming/fencing is a later scheduler layer."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        self._path = path
        connection = open_database(path)
        try:
            migrate_scheduler(connection, now=migration_now)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return open_database(self._path)

    def _require_active_workspace(
        self, connection: sqlite3.Connection, workspace_id: WorkspaceId
    ) -> None:
        row = connection.execute(
            "SELECT archived_at FROM workspaces WHERE workspace_id=?", (str(workspace_id),)
        ).fetchone()
        if row is None:
            raise WorkspaceNotFound(str(workspace_id))
        if row["archived_at"] is not None:
            raise WorkflowConflict("cannot mutate scheduler state in an archived workspace")

    def put_workflow(
        self,
        workspace_id: WorkspaceId,
        workflow: WorkflowDefinition,
        *,
        now: Instant | str,
    ) -> WorkflowDefinition:
        now = Instant(now)
        payload = workflow.to_json()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            existing = connection.execute(
                "SELECT definition_json FROM workflows WHERE workspace_id=? AND workflow_id=?",
                (str(workspace_id), str(workflow.id)),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO workflows(workspace_id,workflow_id,definition_json,created_at,updated_at) "
                    "VALUES (?,?,?,?,?)",
                    (str(workspace_id), str(workflow.id), payload, now, now),
                )
            elif existing["definition_json"] != payload:
                connection.execute(
                    "UPDATE workflows SET definition_json=?,updated_at=?,row_version=row_version+1 "
                    "WHERE workspace_id=? AND workflow_id=?",
                    (payload, now, str(workspace_id), str(workflow.id)),
                )
            connection.execute("COMMIT")
            return workflow
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_workflow(
        self, workspace_id: WorkspaceId, workflow_id: WorkflowId
    ) -> WorkflowDefinition | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT definition_json FROM workflows WHERE workspace_id=? AND workflow_id=?",
                (str(workspace_id), str(workflow_id)),
            ).fetchone()
            return None if row is None else WorkflowDefinition.from_json(row["definition_json"])
        finally:
            connection.close()

    def list_workflows(self, workspace_id: WorkspaceId) -> tuple[WorkflowDefinition, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT definition_json FROM workflows WHERE workspace_id=? ORDER BY workflow_id",
                (str(workspace_id),),
            ).fetchall()
            return tuple(WorkflowDefinition.from_json(row["definition_json"]) for row in rows)
        finally:
            connection.close()

    def put_schedule(
        self, workspace_id: WorkspaceId, schedule: Schedule, *, now: Instant | str
    ) -> Schedule:
        now = Instant(now)
        payload = schedule.to_json()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            workflow = connection.execute(
                "SELECT 1 FROM workflows WHERE workspace_id=? AND workflow_id=?",
                (str(workspace_id), str(schedule.workflow_id)),
            ).fetchone()
            if workflow is None:
                raise WorkflowNotFound(str(schedule.workflow_id))
            existing = connection.execute(
                "SELECT schedule_json FROM schedules WHERE workspace_id=? AND schedule_id=?",
                (str(workspace_id), str(schedule.id)),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO schedules(workspace_id,schedule_id,workflow_id,schedule_json,"
                    "created_at,updated_at) VALUES (?,?,?,?,?,?)",
                    (
                        str(workspace_id),
                        str(schedule.id),
                        str(schedule.workflow_id),
                        payload,
                        now,
                        now,
                    ),
                )
            elif existing["schedule_json"] != payload:
                connection.execute(
                    "UPDATE schedules SET workflow_id=?,schedule_json=?,updated_at=?,"
                    "row_version=row_version+1 WHERE workspace_id=? AND schedule_id=?",
                    (
                        str(schedule.workflow_id),
                        payload,
                        now,
                        str(workspace_id),
                        str(schedule.id),
                    ),
                )
            connection.execute("COMMIT")
            return schedule
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_schedule(self, workspace_id: WorkspaceId, schedule_id: ScheduleId) -> Schedule | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT schedule_json FROM schedules WHERE workspace_id=? AND schedule_id=?",
                (str(workspace_id), str(schedule_id)),
            ).fetchone()
            return None if row is None else Schedule.from_json(row["schedule_json"])
        finally:
            connection.close()

    def create_run(
        self,
        workspace_id: WorkspaceId,
        run_id: WorkflowRunId,
        workflow_id: WorkflowId,
        trigger: Trigger,
        *,
        now: Instant | str,
    ) -> WorkflowRun:
        now = Instant(now)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            workflow_row = connection.execute(
                "SELECT definition_json FROM workflows WHERE workspace_id=? AND workflow_id=?",
                (str(workspace_id), str(workflow_id)),
            ).fetchone()
            if workflow_row is None:
                raise WorkflowNotFound(str(workflow_id))
            workflow = WorkflowDefinition.from_json(workflow_row["definition_json"])
            run = WorkflowRun(run_id, workflow_id, workflow, trigger)
            existing_trigger = connection.execute(
                "SELECT run_json FROM workflow_runs WHERE workspace_id=? AND workflow_id=? "
                "AND trigger_key=?",
                (str(workspace_id), str(workflow_id), trigger.key),
            ).fetchone()
            if existing_trigger is not None:
                existing = WorkflowRun.from_json(existing_trigger["run_json"])
                if existing.trigger == trigger:
                    connection.execute("COMMIT")
                    return existing
                raise WorkflowRunConflict("trigger key already exists with different trigger content")
            existing_id = connection.execute(
                "SELECT 1 FROM workflow_runs WHERE workspace_id=? AND workflow_run_id=?",
                (str(workspace_id), str(run_id)),
            ).fetchone()
            if existing_id is not None:
                raise WorkflowRunConflict(f"workflow run id already exists: {run_id}")
            connection.execute(
                "INSERT INTO workflow_runs(workspace_id,workflow_run_id,workflow_id,trigger_key,state,"
                "run_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    str(workspace_id),
                    str(run_id),
                    str(workflow_id),
                    trigger.key,
                    run.state,
                    run.to_json(),
                    now,
                    now,
                ),
            )
            for node in workflow.pipeline.nodes:
                task_id = _task_run_id(run_id, node.id.value)
                connection.execute(
                    "INSERT INTO task_runs(workspace_id,task_run_id,workflow_run_id,node_id,state,"
                    "attempt_count,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        str(workspace_id),
                        str(task_id),
                        str(run_id),
                        node.id.value,
                        "pending",
                        0,
                        now,
                        now,
                    ),
                )
            connection.execute("COMMIT")
            return run
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_run(self, workspace_id: WorkspaceId, run_id: WorkflowRunId) -> WorkflowRun | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT run_json FROM workflow_runs WHERE workspace_id=? AND workflow_run_id=?",
                (str(workspace_id), str(run_id)),
            ).fetchone()
            return None if row is None else WorkflowRun.from_json(row["run_json"])
        finally:
            connection.close()

    def list_task_runs(
        self, workspace_id: WorkspaceId, run_id: WorkflowRunId
    ) -> tuple[TaskRun, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM task_runs WHERE workspace_id=? AND workflow_run_id=? ORDER BY node_id",
                (str(workspace_id), str(run_id)),
            ).fetchall()
            return tuple(
                TaskRun(
                    id=TaskRunId(row["task_run_id"]),
                    workflow_run_id=WorkflowRunId(row["workflow_run_id"]),
                    node_id=NodeId(row["node_id"]),
                    state=cast(TaskRunState, row["state"]),
                    attempt_count=int(row["attempt_count"]),
                )
                for row in rows
            )
        finally:
            connection.close()
