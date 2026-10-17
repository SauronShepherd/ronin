"""PostgreSQL scheduler run/task snapshot persistence."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast

from studio_core import (
    NodeId,
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
from studio_core.branching import BranchDecision, Scalar, evaluate_branch
from studio_orchestrator import Instant

from .postgres_workflow import PostgresWorkflowBundleImportStore
from .scheduler import (
    WorkflowNotFound,
    WorkflowRunConflict,
    _task_run_id,
)

_SCHEMA_VERSION = 2
_SCHEMA = """
CREATE TABLE ronin_workflow_runs (
    workspace_id TEXT NOT NULL REFERENCES ronin_workspaces(workspace_id) ON DELETE CASCADE,
    workflow_run_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    trigger_key TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN ('pending','running','succeeded','failed','cancelling','cancelled')
    ),
    run_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, workflow_run_id),
    UNIQUE (workspace_id, workflow_id, trigger_key),
    FOREIGN KEY (workspace_id, workflow_id)
        REFERENCES ronin_workflows(workspace_id, workflow_id) ON DELETE CASCADE
);
CREATE TABLE ronin_task_runs (
    workspace_id TEXT NOT NULL,
    task_run_id TEXT NOT NULL,
    workflow_run_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN ('pending','running','retry_wait','succeeded','failed','cancelled','blocked')
    ),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, task_run_id),
    UNIQUE (workspace_id, workflow_run_id, node_id),
    FOREIGN KEY (workspace_id, workflow_run_id)
        REFERENCES ronin_workflow_runs(workspace_id, workflow_run_id) ON DELETE CASCADE
);
CREATE INDEX ronin_workflow_runs_state_idx
    ON ronin_workflow_runs(workspace_id, state, created_at, workflow_run_id);
CREATE INDEX ronin_task_runs_state_idx
    ON ronin_task_runs(workspace_id, state, created_at, task_run_id);
"""


class PostgresSchedulerSnapshotStore(PostgresWorkflowBundleImportStore):
    """PostgreSQL workflow/run/task snapshot store, without dispatch semantics.

    This intentionally does not claim scheduler adapter conformance: fencing,
    execution outbox, events, backfills and task evidence remain separate work.
    """

    def __init__(self, dsn: str, *, application_name: str = "ronin-scheduler-snapshots") -> None:
        super().__init__(dsn, application_name=application_name)
        self.migrate_scheduler()

    def migrate_scheduler(self) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    ("ronin:postgres-scheduler-snapshots",),
                )
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS ronin_scheduler_schema_migrations "
                    "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
                )
                cursor.execute(
                    "SELECT COALESCE(MAX(version),0) AS version "
                    "FROM ronin_scheduler_schema_migrations"
                )
                current = int(cursor.fetchone()["version"])
                if current > _SCHEMA_VERSION:
                    raise RuntimeError(
                        f"PostgreSQL scheduler schema {current} is newer than supported "
                        f"{_SCHEMA_VERSION}"
                    )
                if current == 0:
                    cursor.execute(_SCHEMA)
                    cursor.execute(
                        "INSERT INTO ronin_scheduler_schema_migrations(version,applied_at) "
                        "VALUES (%s,%s)",
                        (
                            1,
                            datetime.now(UTC)
                            .isoformat(timespec="microseconds")
                            .replace("+00:00", "Z"),
                        ),
                    )
                    current = 1
                if current == 1:
                    cursor.execute(
                        "ALTER TABLE ronin_task_runs ADD COLUMN branch_decision_json TEXT"
                    )
                    cursor.execute(
                        "INSERT INTO ronin_scheduler_schema_migrations(version,applied_at) "
                        "VALUES (%s,%s)",
                        (
                            2,
                            datetime.now(UTC)
                            .isoformat(timespec="microseconds")
                            .replace("+00:00", "Z"),
                        ),
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
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
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_active_workspace(cursor, workspace_id)
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s),hashtext(%s))",
                    (str(workspace_id), str(run_id)),
                )
                cursor.execute(
                    "SELECT definition_json FROM ronin_workflows "
                    "WHERE workspace_id=%s AND workflow_id=%s FOR UPDATE",
                    (str(workspace_id), str(workflow_id)),
                )
                workflow_row = cursor.fetchone()
                if workflow_row is None:
                    raise WorkflowNotFound(str(workflow_id))
                workflow = WorkflowDefinition.from_json(workflow_row["definition_json"])
                cursor.execute(
                    "SELECT run_json FROM ronin_workflow_runs "
                    "WHERE workspace_id=%s AND workflow_id=%s AND trigger_key=%s FOR UPDATE",
                    (str(workspace_id), str(workflow_id), trigger.key),
                )
                existing_trigger = cursor.fetchone()
                if existing_trigger is not None:
                    existing = WorkflowRun.from_json(existing_trigger["run_json"])
                    if existing.trigger != trigger:
                        raise WorkflowRunConflict(
                            "trigger key already exists with different trigger content"
                        )
                    connection.commit()
                    return existing

                cursor.execute(
                    "SELECT 1 FROM ronin_workflow_runs "
                    "WHERE workspace_id=%s AND workflow_run_id=%s",
                    (str(workspace_id), str(run_id)),
                )
                if cursor.fetchone() is not None:
                    raise WorkflowRunConflict(f"workflow run id already exists: {run_id}")

                run = WorkflowRun(run_id, workflow_id, workflow, trigger)
                cursor.execute(
                    "INSERT INTO ronin_workflow_runs "
                    "(workspace_id,workflow_run_id,workflow_id,trigger_key,state,run_json,"
                    "created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        str(workspace_id),
                        str(run_id),
                        str(workflow_id),
                        trigger.key,
                        run.state,
                        run.to_json(),
                        str(current),
                        str(current),
                    ),
                )
                for node in workflow.pipeline.nodes:
                    task_id = _task_run_id(run_id, node.id.value)
                    cursor.execute(
                        "INSERT INTO ronin_task_runs "
                        "(workspace_id,task_run_id,workflow_run_id,node_id,state,attempt_count,"
                        "created_at,updated_at) VALUES (%s,%s,%s,%s,'pending',0,%s,%s)",
                        (
                            str(workspace_id),
                            str(task_id),
                            str(run_id),
                            node.id.value,
                            str(current),
                            str(current),
                        ),
                    )
            connection.commit()
            return run
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_run(self, workspace_id: WorkspaceId, run_id: WorkflowRunId) -> WorkflowRun | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT run_json FROM ronin_workflow_runs "
                    "WHERE workspace_id=%s AND workflow_run_id=%s",
                    (str(workspace_id), str(run_id)),
                )
                row = cursor.fetchone()
            return None if row is None else WorkflowRun.from_json(row["run_json"])
        finally:
            connection.close()

    def list_task_runs(
        self,
        workspace_id: WorkspaceId,
        run_id: WorkflowRunId,
    ) -> tuple[TaskRun, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT task_run_id,workflow_run_id,node_id,state,attempt_count "
                    "FROM ronin_task_runs WHERE workspace_id=%s AND workflow_run_id=%s "
                    "ORDER BY node_id",
                    (str(workspace_id), str(run_id)),
                )
                rows = cursor.fetchall()
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

    def apply_branch_decision(
        self,
        workspace_id: WorkspaceId,
        run_id: WorkflowRunId,
        node_id: NodeId,
        expression: object,
        context: Mapping[str, object],
        *,
        now: Instant | str,
    ) -> BranchDecision:
        """Persist one replay-safe branch decision for a task run."""
        current = Instant(now)
        decision = evaluate_branch(expression, cast(Mapping[str, Scalar], context))
        task_id = _task_run_id(run_id, node_id.value)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT state,branch_decision_json FROM ronin_task_runs "
                    "WHERE workspace_id=%s AND workflow_run_id=%s AND node_id=%s FOR UPDATE",
                    (str(workspace_id), str(run_id), node_id.value),
                )
                row = cursor.fetchone()
                if row is None:
                    raise WorkflowNotFound(f"task run for node {node_id} does not exist")
                payload = decision.to_json()
                if (
                    row["branch_decision_json"] is not None
                    and row["branch_decision_json"] != payload
                ):
                    raise WorkflowRunConflict(
                        "branch decision already persisted with different content"
                    )
                if row["branch_decision_json"] is None:
                    if row["state"] != "pending":
                        raise WorkflowRunConflict(
                            "branch decision cannot be added after task execution has started"
                        )
                    cursor.execute(
                        "UPDATE ronin_task_runs SET state=%s,branch_decision_json=%s,"
                        "updated_at=%s,row_version=row_version+1 "
                        "WHERE workspace_id=%s AND task_run_id=%s",
                        (
                            "pending" if decision.should_run else "blocked",
                            payload,
                            str(current),
                            str(workspace_id),
                            str(task_id),
                        ),
                    )
            connection.commit()
            return decision
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_branch_decision(
        self,
        workspace_id: WorkspaceId,
        run_id: WorkflowRunId,
        node_id: NodeId,
    ) -> BranchDecision | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT branch_decision_json FROM ronin_task_runs "
                    "WHERE workspace_id=%s AND workflow_run_id=%s AND node_id=%s",
                    (str(workspace_id), str(run_id), node_id.value),
                )
                row = cursor.fetchone()
            if row is None or row["branch_decision_json"] is None:
                return None
            return BranchDecision.from_json(row["branch_decision_json"])
        finally:
            connection.close()


__all__ = ("PostgresSchedulerSnapshotStore",)
