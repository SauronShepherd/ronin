"""Durable scheduler execution links, outbox intents and terminal reconciliation."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from studio_core import NodeId, TaskRunId, WorkflowRunId, WorkspaceId
from studio_orchestrator import (
    Instant,
    Job,
    JobId,
    JobState,
    LeaseToken,
    Run,
    RunState,
)

from .scheduler_fencing import (
    FencedSqliteSchedulerStore,
    TaskAttemptId,
    migrate_scheduler_fencing,
)
from .sqlite import open_database

_EXECUTION_LINK_SCHEMA_VERSION = 2
_EXECUTION_LINK_MIGRATIONS = {
    1: "scheduler_execution_001.sql",
    2: "scheduler_execution_002_outbox.sql",
}


class TaskExecutionLinkConflict(RuntimeError):
    """Raised when a task attempt is rebound to different execution identity."""


@dataclass(frozen=True, slots=True)
class TaskExecutionLink:
    workspace_id: WorkspaceId
    task_attempt_id: TaskAttemptId
    job_id: JobId
    request_digest: str

    def __post_init__(self) -> None:
        if len(self.request_digest) != 64 or any(
            char not in "0123456789abcdef" for char in self.request_digest
        ):
            raise ValueError("request_digest must be lowercase sha256 hex")


@dataclass(frozen=True, slots=True)
class TaskExecutionIntent:
    """One idempotently dispatchable Job/Run candidate persisted before submission."""

    workspace_id: WorkspaceId
    task_attempt_id: TaskAttemptId
    job: Job
    run: Run

    def __post_init__(self) -> None:
        if self.run.job_id != self.job.id:
            raise ValueError("execution intent run must belong to its job")
        if self.job.state is not JobState.QUEUED:
            raise ValueError("execution intent job must start queued")
        if self.run.state is not RunState.PENDING or self.run.ordinal != 1:
            raise ValueError("execution intent run must be initial pending run")

    @property
    def link(self) -> TaskExecutionLink:
        return TaskExecutionLink(
            self.workspace_id,
            self.task_attempt_id,
            self.job.id,
            self.job.request_digest,
        )


def _execute_script_in_transaction(connection: sqlite3.Connection, script: str) -> None:
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)


def migrate_scheduler_execution(connection: sqlite3.Connection, *, now: Instant | str) -> None:
    now = Instant(now)
    migrate_scheduler_fencing(connection, now=now)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS scheduler_execution_schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = connection.execute(
        "SELECT MAX(version) AS version FROM scheduler_execution_schema_migrations"
    ).fetchone()
    current = 0 if row is None or row["version"] is None else int(row["version"])
    if current > _EXECUTION_LINK_SCHEMA_VERSION:
        raise RuntimeError(
            f"scheduler execution schema {current} is newer than supported "
            f"{_EXECUTION_LINK_SCHEMA_VERSION}"
        )
    migrations_dir = Path(__file__).with_name("migrations")
    for version in range(current + 1, _EXECUTION_LINK_SCHEMA_VERSION + 1):
        script = migrations_dir.joinpath(_EXECUTION_LINK_MIGRATIONS[version]).read_text(
            encoding="utf-8"
        )
        connection.execute("BEGIN IMMEDIATE")
        try:
            _execute_script_in_transaction(connection, script)
            connection.execute(
                "INSERT INTO scheduler_execution_schema_migrations(version,applied_at) "
                "VALUES (?,?)",
                (version, now),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def scheduler_execution_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT MAX(version) AS version FROM scheduler_execution_schema_migrations"
    ).fetchone()
    return 0 if row is None or row["version"] is None else int(row["version"])


def _intent_from_row(row: sqlite3.Row) -> TaskExecutionIntent:
    created_at = Instant(row["created_at"])
    job = Job(
        id=JobId(row["job_id"]),
        project_id=row["project_id"],
        idempotency_key=row["idempotency_key"],
        request_digest=row["request_digest"],
        state=JobState.QUEUED,
        created_at=created_at,
        updated_at=created_at,
        target=row["target"],
        parameters_json=row["parameters_json"],
    )
    run = Run(
        id=__import__("studio_orchestrator").RunId(row["run_id"]),
        job_id=job.id,
        ordinal=1,
        state=RunState.PENDING,
        not_before=Instant(row["not_before"]),
        created_at=created_at,
        updated_at=created_at,
    )
    return TaskExecutionIntent(
        WorkspaceId(row["workspace_id"]),
        TaskAttemptId(row["task_attempt_id"]),
        job,
        run,
    )


class SchedulerExecutionLinkStore(FencedSqliteSchedulerStore):
    """Fenced scheduler store with durable execution outbox/reconciliation state."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        super().__init__(path, migration_now=migration_now)
        connection = open_database(path)
        try:
            migrate_scheduler_execution(connection, now=migration_now)
        finally:
            connection.close()

    def bind_execution(
        self,
        workspace_id: WorkspaceId,
        attempt_id: TaskAttemptId,
        *,
        job_id: JobId,
        request_digest: str,
        owner: str,
        lease_token: LeaseToken,
        now: Instant | str,
    ) -> TaskExecutionLink:
        current = Instant(now)
        link = TaskExecutionLink(workspace_id, attempt_id, job_id, request_digest)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._active_attempt(
                connection,
                workspace_id,
                attempt_id,
                owner=owner,
                lease_token=lease_token,
                now=current,
            )
            existing = connection.execute(
                "SELECT job_id,request_digest FROM task_execution_links "
                "WHERE workspace_id=? AND task_attempt_id=?",
                (str(workspace_id), str(attempt_id)),
            ).fetchone()
            if existing is not None:
                if existing["job_id"] != str(job_id) or existing["request_digest"] != request_digest:
                    raise TaskExecutionLinkConflict(
                        "task attempt is already bound to different execution identity"
                    )
                connection.execute("COMMIT")
                return link
            connection.execute(
                "INSERT INTO task_execution_links("
                "workspace_id,task_attempt_id,job_id,request_digest,created_at) VALUES (?,?,?,?,?)",
                (str(workspace_id), str(attempt_id), str(job_id), request_digest, current),
            )
            connection.execute("COMMIT")
            return link
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def put_execution_intent(
        self,
        workspace_id: WorkspaceId,
        attempt_id: TaskAttemptId,
        *,
        job: Job,
        run: Run,
        owner: str,
        lease_token: LeaseToken,
        now: Instant | str,
    ) -> TaskExecutionIntent:
        """Persist executable intent atomically with its fenced task/job link."""

        current = Instant(now)
        intent = TaskExecutionIntent(workspace_id, attempt_id, job, run)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._active_attempt(
                connection,
                workspace_id,
                attempt_id,
                owner=owner,
                lease_token=lease_token,
                now=current,
            )
            link = connection.execute(
                "SELECT job_id,request_digest FROM task_execution_links "
                "WHERE workspace_id=? AND task_attempt_id=?",
                (str(workspace_id), str(attempt_id)),
            ).fetchone()
            if link is None:
                connection.execute(
                    "INSERT INTO task_execution_links("
                    "workspace_id,task_attempt_id,job_id,request_digest,created_at) "
                    "VALUES (?,?,?,?,?)",
                    (
                        str(workspace_id),
                        str(attempt_id),
                        str(job.id),
                        job.request_digest,
                        current,
                    ),
                )
            elif link["job_id"] != str(job.id) or link["request_digest"] != job.request_digest:
                raise TaskExecutionLinkConflict(
                    "task attempt is already bound to different execution identity"
                )

            existing = connection.execute(
                "SELECT * FROM task_execution_intents "
                "WHERE workspace_id=? AND task_attempt_id=?",
                (str(workspace_id), str(attempt_id)),
            ).fetchone()
            if existing is not None:
                found = _intent_from_row(existing)
                if found != intent:
                    raise TaskExecutionLinkConflict(
                        "task attempt already has a different execution intent"
                    )
                connection.execute("COMMIT")
                return found
            connection.execute(
                "INSERT INTO task_execution_intents("
                "workspace_id,task_attempt_id,job_id,run_id,project_id,idempotency_key,"
                "request_digest,target,parameters_json,created_at,not_before) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(workspace_id),
                    str(attempt_id),
                    str(job.id),
                    str(run.id),
                    job.project_id,
                    job.idempotency_key,
                    job.request_digest,
                    job.target,
                    job.parameters_json,
                    job.created_at,
                    run.not_before,
                ),
            )
            connection.execute("COMMIT")
            return intent
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_execution_link(
        self,
        workspace_id: WorkspaceId,
        attempt_id: TaskAttemptId,
    ) -> TaskExecutionLink | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT job_id,request_digest FROM task_execution_links "
                "WHERE workspace_id=? AND task_attempt_id=?",
                (str(workspace_id), str(attempt_id)),
            ).fetchone()
            if row is None:
                return None
            return TaskExecutionLink(
                workspace_id,
                attempt_id,
                JobId(row["job_id"]),
                row["request_digest"],
            )
        finally:
            connection.close()

    def get_execution_intent(
        self,
        workspace_id: WorkspaceId,
        attempt_id: TaskAttemptId,
    ) -> TaskExecutionIntent | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM task_execution_intents "
                "WHERE workspace_id=? AND task_attempt_id=?",
                (str(workspace_id), str(attempt_id)),
            ).fetchone()
            return None if row is None else _intent_from_row(row)
        finally:
            connection.close()

    def list_execution_intents(self, *, limit: int = 100) -> tuple[TaskExecutionIntent, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("execution intent limit must be between 1 and 1000")
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM task_execution_intents ORDER BY created_at,task_attempt_id LIMIT ?",
                (limit,),
            ).fetchall()
            return tuple(_intent_from_row(row) for row in rows)
        finally:
            connection.close()

    def _reclaim_expired_in_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        now: Instant,
    ) -> int:
        """Do not duplicate scheduler attempts once durable execution intent exists."""

        rows = connection.execute(
            "SELECT * FROM task_attempts WHERE state='running' AND lease_expires_at<=? "
            "ORDER BY workspace_id,task_attempt_id",
            (now,),
        ).fetchall()
        reclaimed = 0
        for attempt in rows:
            intent = connection.execute(
                "SELECT 1 FROM task_execution_intents "
                "WHERE workspace_id=? AND task_attempt_id=?",
                (attempt["workspace_id"], attempt["task_attempt_id"]),
            ).fetchone()
            if intent is not None:
                continue
            workspace_id = WorkspaceId(attempt["workspace_id"])
            task_row = connection.execute(
                "SELECT * FROM task_runs WHERE workspace_id=? AND task_run_id=?",
                (str(workspace_id), attempt["task_run_id"]),
            ).fetchone()
            if task_row is None:
                raise AssertionError("task attempt references missing task run")
            run = self._workflow_state(
                connection,
                workspace_id,
                WorkflowRunId(task_row["workflow_run_id"]),
            )
            connection.execute(
                "UPDATE task_attempts SET state='lost',failure_code='lease_expired',"
                "updated_at=? WHERE workspace_id=? AND task_attempt_id=? AND state='running'",
                (now, str(workspace_id), attempt["task_attempt_id"]),
            )
            self._mark_failure_or_retry(
                connection,
                workspace_id,
                run,
                task_run_id=TaskRunId(task_row["task_run_id"]),
                node_id=NodeId(task_row["node_id"]),
                attempt_ordinal=int(attempt["ordinal"]),
                now=now,
            )
            reclaimed += 1
        return reclaimed

    def reconcile_execution(
        self,
        workspace_id: WorkspaceId,
        attempt_id: TaskAttemptId,
        job: Job,
        *,
        now: Instant | str,
    ) -> bool:
        """Project a terminal linked Job result back into scheduler task state.

        Returns ``False`` for non-terminal jobs and for cancellation, whose
        propagation semantics remain a separate Public v1 slice.
        """

        if job.state not in {JobState.SUCCEEDED, JobState.FAILED}:
            return False
        current = Instant(now)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            intent_row = connection.execute(
                "SELECT * FROM task_execution_intents "
                "WHERE workspace_id=? AND task_attempt_id=?",
                (str(workspace_id), str(attempt_id)),
            ).fetchone()
            if intent_row is None:
                raise KeyError(f"execution intent does not exist: {workspace_id}/{attempt_id}")
            intent = _intent_from_row(intent_row)
            if intent.job.id != job.id or intent.job.request_digest != job.request_digest:
                raise TaskExecutionLinkConflict("terminal job does not match execution intent")

            attempt = connection.execute(
                "SELECT * FROM task_attempts WHERE workspace_id=? AND task_attempt_id=?",
                (str(workspace_id), str(attempt_id)),
            ).fetchone()
            if attempt is None:
                raise KeyError(str(attempt_id))
            task = connection.execute(
                "SELECT * FROM task_runs WHERE workspace_id=? AND task_run_id=?",
                (str(workspace_id), attempt["task_run_id"]),
            ).fetchone()
            if task is None:
                raise AssertionError("task attempt references missing task run")
            if task["state"] in {"succeeded", "failed"}:
                connection.execute("COMMIT")
                return True
            workflow = self._workflow_state(
                connection,
                workspace_id,
                WorkflowRunId(task["workflow_run_id"]),
            )
            if job.state is JobState.SUCCEEDED:
                connection.execute(
                    "UPDATE task_attempts SET state='succeeded',failure_code=NULL,updated_at=? "
                    "WHERE workspace_id=? AND task_attempt_id=?",
                    (current, str(workspace_id), str(attempt_id)),
                )
                connection.execute(
                    "UPDATE task_runs SET state='succeeded',next_eligible_at=NULL,updated_at=?,"
                    "row_version=row_version+1 WHERE workspace_id=? AND task_run_id=?",
                    (current, str(workspace_id), task["task_run_id"]),
                )
                remaining = connection.execute(
                    "SELECT COUNT(*) AS count FROM task_runs WHERE workspace_id=? "
                    "AND workflow_run_id=? AND state!='succeeded'",
                    (str(workspace_id), str(workflow.id)),
                ).fetchone()
                if remaining is None:
                    raise AssertionError("workflow completion query returned no row")
                if int(remaining["count"]) == 0:
                    self._write_workflow_state(
                        connection,
                        workspace_id,
                        workflow,
                        state="succeeded",
                        now=current,
                    )
            else:
                failure_code = job.failure_code or "execution_failed"
                connection.execute(
                    "UPDATE task_attempts SET state='failed',failure_code=?,updated_at=? "
                    "WHERE workspace_id=? AND task_attempt_id=?",
                    (failure_code, current, str(workspace_id), str(attempt_id)),
                )
                self._mark_failure_or_retry(
                    connection,
                    workspace_id,
                    workflow,
                    task_run_id=TaskRunId(task["task_run_id"]),
                    node_id=NodeId(task["node_id"]),
                    attempt_ordinal=int(attempt["ordinal"]),
                    now=current,
                )
            connection.execute("COMMIT")
            return True
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()


__all__ = (
    "SchedulerExecutionLinkStore",
    "TaskExecutionIntent",
    "TaskExecutionLink",
    "TaskExecutionLinkConflict",
    "migrate_scheduler_execution",
    "scheduler_execution_schema_version",
)
