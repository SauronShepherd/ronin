"""Lease-fenced durable task dispatch for Public v1 workflows."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from studio_core import NodeId, TaskRunId, WorkflowRun, WorkflowRunId, WorkspaceId
from studio_orchestrator import Instant, LeaseToken

from .scheduler import SqliteSchedulerStore, migrate_scheduler
from .sqlite import open_database

_FENCING_SCHEMA_VERSION = 1
_FENCING_MIGRATIONS = {1: "scheduler_002_fencing.sql"}


@dataclass(frozen=True, order=True, slots=True)
class TaskAttemptId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or self.value != self.value.strip():
            raise ValueError("task attempt id must be non-empty and trimmed")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ClaimedTask:
    workspace_id: WorkspaceId
    workflow_run_id: WorkflowRunId
    task_run_id: TaskRunId
    node_id: NodeId
    attempt_id: TaskAttemptId
    attempt_ordinal: int
    lease_owner: str
    lease_token: LeaseToken
    lease_expires_at: Instant


def _add_seconds(value: Instant | str, seconds: int) -> Instant:
    base = Instant(value)
    parsed = datetime.strptime(str(base), "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    return Instant(
        (parsed + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )


def _execute_script_in_transaction(connection: sqlite3.Connection, script: str) -> None:
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)


def migrate_scheduler_fencing(
    connection: sqlite3.Connection,
    *,
    now: Instant | str,
) -> None:
    now = Instant(now)
    migrate_scheduler(connection, now=now)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS scheduler_fencing_schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = connection.execute(
        "SELECT MAX(version) AS version FROM scheduler_fencing_schema_migrations"
    ).fetchone()
    current = 0 if row is None or row["version"] is None else int(row["version"])
    if current > _FENCING_SCHEMA_VERSION:
        raise RuntimeError(
            f"scheduler fencing schema {current} is newer than supported "
            f"{_FENCING_SCHEMA_VERSION}"
        )
    migrations_dir = Path(__file__).with_name("migrations")
    for version in range(current + 1, _FENCING_SCHEMA_VERSION + 1):
        script = migrations_dir.joinpath(_FENCING_MIGRATIONS[version]).read_text(
            encoding="utf-8"
        )
        connection.execute("BEGIN IMMEDIATE")
        try:
            _execute_script_in_transaction(connection, script)
            connection.execute(
                "INSERT INTO scheduler_fencing_schema_migrations(version,applied_at) "
                "VALUES (?,?)",
                (version, now),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def scheduler_fencing_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT MAX(version) AS version FROM scheduler_fencing_schema_migrations"
    ).fetchone()
    return 0 if row is None or row["version"] is None else int(row["version"])


class FencedSqliteSchedulerStore(SqliteSchedulerStore):
    """Scheduler store whose worker-originated state transitions require a live lease."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        super().__init__(path, migration_now=migration_now)
        connection = open_database(path)
        try:
            migrate_scheduler_fencing(connection, now=migration_now)
        finally:
            connection.close()

    def _active_attempt(
        self,
        connection: sqlite3.Connection,
        workspace_id: WorkspaceId,
        attempt_id: TaskAttemptId,
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant,
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM task_attempts WHERE workspace_id=? AND task_attempt_id=? "
            "AND state='running' AND lease_owner=? AND lease_token=? "
            "AND lease_expires_at>?",
            (
                str(workspace_id),
                str(attempt_id),
                owner,
                str(lease_token),
                now,
            ),
        ).fetchone()
        if row is None:
            raise ValueError("task attempt lease ownership lost")
        return row

    @staticmethod
    def _workflow_state(
        connection: sqlite3.Connection,
        workspace_id: WorkspaceId,
        run_id: WorkflowRunId,
    ) -> WorkflowRun:
        row = connection.execute(
            "SELECT run_json FROM workflow_runs WHERE workspace_id=? AND workflow_run_id=?",
            (str(workspace_id), str(run_id)),
        ).fetchone()
        if row is None:
            raise KeyError(str(run_id))
        return WorkflowRun.from_json(row["run_json"])

    @staticmethod
    def _write_workflow_state(
        connection: sqlite3.Connection,
        workspace_id: WorkspaceId,
        run: WorkflowRun,
        *,
        state: str,
        now: Instant,
    ) -> None:
        updated = replace(run, state=state)
        connection.execute(
            "UPDATE workflow_runs SET state=?,run_json=?,updated_at=?,"
            "row_version=row_version+1 WHERE workspace_id=? AND workflow_run_id=?",
            (
                state,
                updated.to_json(),
                now,
                str(workspace_id),
                str(run.id),
            ),
        )

    @staticmethod
    def _predecessor_ids(run: WorkflowRun, node_id: NodeId) -> tuple[str, ...]:
        return tuple(
            sorted(
                edge.source.value
                for edge in run.workflow_snapshot.pipeline.edges
                if edge.target == node_id
            )
        )

    @staticmethod
    def _task_policy(run: WorkflowRun, node_id: NodeId):
        return run.workflow_snapshot.policy_for(node_id)

    def _mark_failure_or_retry(
        self,
        connection: sqlite3.Connection,
        workspace_id: WorkspaceId,
        run: WorkflowRun,
        *,
        task_run_id: TaskRunId,
        node_id: NodeId,
        attempt_ordinal: int,
        now: Instant,
    ) -> None:
        policy = self._task_policy(run, node_id)
        if attempt_ordinal < policy.retry.max_attempts:
            multiplier = 2 ** (attempt_ordinal - 1) if policy.retry.exponential_backoff else 1
            delay = policy.retry.delay_seconds * multiplier
            next_eligible = _add_seconds(now, delay)
            connection.execute(
                "UPDATE task_runs SET state='retry_wait',next_eligible_at=?,updated_at=?,"
                "row_version=row_version+1 WHERE workspace_id=? AND task_run_id=?",
                (next_eligible, now, str(workspace_id), str(task_run_id)),
            )
            return
        connection.execute(
            "UPDATE task_runs SET state='failed',next_eligible_at=NULL,updated_at=?,"
            "row_version=row_version+1 WHERE workspace_id=? AND task_run_id=?",
            (now, str(workspace_id), str(task_run_id)),
        )
        self._write_workflow_state(
            connection,
            workspace_id,
            run,
            state="failed",
            now=now,
        )

    def _reclaim_expired_in_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        now: Instant,
    ) -> int:
        rows = connection.execute(
            "SELECT * FROM task_attempts WHERE state='running' AND lease_expires_at<=? "
            "ORDER BY workspace_id,task_attempt_id",
            (now,),
        ).fetchall()
        reclaimed = 0
        for attempt in rows:
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

    def reclaim_expired(self, *, now: Instant | str) -> int:
        current = Instant(now)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            reclaimed = self._reclaim_expired_in_transaction(connection, now=current)
            connection.execute("COMMIT")
            return reclaimed
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def claim_next_task(
        self,
        *,
        owner: str,
        lease_token: LeaseToken,
        attempt_id: TaskAttemptId,
        lease_seconds: int,
        now: Instant | str,
        workspace_id: WorkspaceId | None = None,
    ) -> ClaimedTask | None:
        if not owner or owner != owner.strip():
            raise ValueError("task lease owner must be non-empty and trimmed")
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        current = Instant(now)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._reclaim_expired_in_transaction(connection, now=current)
            clauses = [
                "t.state IN ('pending','retry_wait')",
                "(t.next_eligible_at IS NULL OR t.next_eligible_at<=?)",
                "w.state IN ('pending','running')",
            ]
            values: list[object] = [current]
            if workspace_id is not None:
                clauses.append("t.workspace_id=?")
                values.append(str(workspace_id))
            rows = connection.execute(
                "SELECT t.* FROM task_runs t JOIN workflow_runs w "
                "ON w.workspace_id=t.workspace_id "
                "AND w.workflow_run_id=t.workflow_run_id WHERE "
                + " AND ".join(clauses)
                + " ORDER BY t.created_at,t.task_run_id",
                tuple(values),
            ).fetchall()
            for task in rows:
                task_workspace = WorkspaceId(task["workspace_id"])
                run = self._workflow_state(
                    connection,
                    task_workspace,
                    WorkflowRunId(task["workflow_run_id"]),
                )
                node_id = NodeId(task["node_id"])
                predecessors = self._predecessor_ids(run, node_id)
                if predecessors:
                    placeholders = ",".join("?" for _ in predecessors)
                    predecessor_rows = connection.execute(
                        "SELECT node_id,state FROM task_runs WHERE workspace_id=? "
                        "AND workflow_run_id=? AND node_id IN ("
                        + placeholders
                        + ")",
                        (
                            str(task_workspace),
                            str(run.id),
                            *predecessors,
                        ),
                    ).fetchall()
                    states = {row["node_id"]: row["state"] for row in predecessor_rows}
                    if any(
                        states.get(predecessor) in {"failed", "cancelled", "blocked"}
                        for predecessor in predecessors
                    ):
                        connection.execute(
                            "UPDATE task_runs SET state='blocked',updated_at=?,"
                            "row_version=row_version+1 WHERE workspace_id=? AND task_run_id=?",
                            (current, str(task_workspace), task["task_run_id"]),
                        )
                        continue
                    if any(states.get(predecessor) != "succeeded" for predecessor in predecessors):
                        continue
                max_concurrency = run.workflow_snapshot.max_concurrency
                if max_concurrency is not None:
                    active = connection.execute(
                        "SELECT COUNT(*) AS count FROM task_runs WHERE workspace_id=? "
                        "AND workflow_run_id=? AND state='running'",
                        (str(task_workspace), str(run.id)),
                    ).fetchone()
                    if active is None:
                        raise AssertionError("task concurrency query returned no row")
                    if int(active["count"]) >= max_concurrency:
                        continue
                policy = self._task_policy(run, node_id)
                ordinal = int(task["attempt_count"]) + 1
                if ordinal > policy.retry.max_attempts:
                    connection.execute(
                        "UPDATE task_runs SET state='failed',updated_at=?,"
                        "row_version=row_version+1 WHERE workspace_id=? AND task_run_id=?",
                        (current, str(task_workspace), task["task_run_id"]),
                    )
                    self._write_workflow_state(
                        connection,
                        task_workspace,
                        run,
                        state="failed",
                        now=current,
                    )
                    continue
                expiry = _add_seconds(current, lease_seconds)
                connection.execute(
                    "INSERT INTO task_attempts(workspace_id,task_attempt_id,task_run_id,ordinal,"
                    "state,lease_owner,lease_token,lease_expires_at,heartbeat_at,failure_code,"
                    "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        str(task_workspace),
                        str(attempt_id),
                        task["task_run_id"],
                        ordinal,
                        "running",
                        owner,
                        str(lease_token),
                        expiry,
                        current,
                        None,
                        current,
                        current,
                    ),
                )
                connection.execute(
                    "UPDATE task_runs SET state='running',attempt_count=?,next_eligible_at=NULL,"
                    "updated_at=?,row_version=row_version+1 "
                    "WHERE workspace_id=? AND task_run_id=?",
                    (
                        ordinal,
                        current,
                        str(task_workspace),
                        task["task_run_id"],
                    ),
                )
                if run.state == "pending":
                    self._write_workflow_state(
                        connection,
                        task_workspace,
                        run,
                        state="running",
                        now=current,
                    )
                connection.execute("COMMIT")
                return ClaimedTask(
                    workspace_id=task_workspace,
                    workflow_run_id=run.id,
                    task_run_id=TaskRunId(task["task_run_id"]),
                    node_id=node_id,
                    attempt_id=attempt_id,
                    attempt_ordinal=ordinal,
                    lease_owner=owner,
                    lease_token=lease_token,
                    lease_expires_at=expiry,
                )
            connection.execute("COMMIT")
            return None
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def heartbeat_task(
        self,
        workspace_id: WorkspaceId,
        attempt_id: TaskAttemptId,
        *,
        owner: str,
        lease_token: LeaseToken,
        lease_seconds: int,
        now: Instant | str,
    ) -> Instant:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        current = Instant(now)
        expiry = _add_seconds(current, lease_seconds)
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
            connection.execute(
                "UPDATE task_attempts SET heartbeat_at=?,lease_expires_at=?,updated_at=? "
                "WHERE workspace_id=? AND task_attempt_id=?",
                (current, expiry, current, str(workspace_id), str(attempt_id)),
            )
            connection.execute("COMMIT")
            return expiry
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def complete_task(
        self,
        workspace_id: WorkspaceId,
        attempt_id: TaskAttemptId,
        *,
        owner: str,
        lease_token: LeaseToken,
        succeeded: bool,
        failure_code: str | None,
        now: Instant | str,
    ) -> None:
        current = Instant(now)
        if succeeded and failure_code is not None:
            raise ValueError("successful task attempt cannot include failure_code")
        if not succeeded and failure_code is None:
            raise ValueError("failed task attempt requires failure_code")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            attempt = self._active_attempt(
                connection,
                workspace_id,
                attempt_id,
                owner=owner,
                lease_token=lease_token,
                now=current,
            )
            task = connection.execute(
                "SELECT * FROM task_runs WHERE workspace_id=? AND task_run_id=?",
                (str(workspace_id), attempt["task_run_id"]),
            ).fetchone()
            if task is None:
                raise AssertionError("task attempt references missing task run")
            run = self._workflow_state(
                connection,
                workspace_id,
                WorkflowRunId(task["workflow_run_id"]),
            )
            attempt_state = "succeeded" if succeeded else "failed"
            connection.execute(
                "UPDATE task_attempts SET state=?,failure_code=?,updated_at=? "
                "WHERE workspace_id=? AND task_attempt_id=?",
                (
                    attempt_state,
                    failure_code,
                    current,
                    str(workspace_id),
                    str(attempt_id),
                ),
            )
            if succeeded:
                connection.execute(
                    "UPDATE task_runs SET state='succeeded',next_eligible_at=NULL,updated_at=?,"
                    "row_version=row_version+1 WHERE workspace_id=? AND task_run_id=?",
                    (current, str(workspace_id), task["task_run_id"]),
                )
                remaining = connection.execute(
                    "SELECT COUNT(*) AS count FROM task_runs WHERE workspace_id=? "
                    "AND workflow_run_id=? AND state!='succeeded'",
                    (str(workspace_id), str(run.id)),
                ).fetchone()
                if remaining is None:
                    raise AssertionError("workflow completion query returned no row")
                if int(remaining["count"]) == 0:
                    self._write_workflow_state(
                        connection,
                        workspace_id,
                        run,
                        state="succeeded",
                        now=current,
                    )
            else:
                self._mark_failure_or_retry(
                    connection,
                    workspace_id,
                    run,
                    task_run_id=TaskRunId(task["task_run_id"]),
                    node_id=NodeId(task["node_id"]),
                    attempt_ordinal=int(attempt["ordinal"]),
                    now=current,
                )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
