"""PostgreSQL scheduler run/task snapshot persistence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast

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
    WorkflowRunState,
    WorkspaceId,
)
from studio_core.branching import BranchDecision, Scalar, evaluate_branch
from studio_core.scheduler_resources import ResourcePoolDefinition
from studio_orchestrator import Instant, LeaseToken

from .postgres_workflow import PostgresWorkflowBundleImportStore
from .scheduler import (
    WorkflowNotFound,
    WorkflowRunConflict,
    _task_run_id,
)
from .scheduler_fencing import ClaimedTask, TaskAttemptId

_SCHEMA_VERSION = 3
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
    """PostgreSQL workflow/run/task persistence with lease-fenced task attempts.

    This intentionally does not claim complete scheduler adapter conformance:
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
                    current = 2
                if current == 2:
                    cursor.execute("ALTER TABLE ronin_task_runs ADD COLUMN next_eligible_at TEXT")
                    cursor.execute(
                        "CREATE TABLE ronin_task_attempts ("
                        "workspace_id TEXT NOT NULL,task_attempt_id TEXT NOT NULL,"
                        "task_run_id TEXT NOT NULL,ordinal INTEGER NOT NULL CHECK (ordinal >= 1),"
                        "state TEXT NOT NULL CHECK "
                        "(state IN ('running','succeeded','failed','lost')),"
                        "lease_owner TEXT NOT NULL,lease_token TEXT NOT NULL,"
                        "lease_expires_at TEXT NOT NULL,heartbeat_at TEXT NOT NULL,"
                        "failure_code TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,"
                        "pool_name TEXT,PRIMARY KEY(workspace_id,task_attempt_id),"
                        "UNIQUE(workspace_id,task_run_id,ordinal),"
                        "FOREIGN KEY(workspace_id,task_run_id) "
                        "REFERENCES ronin_task_runs(workspace_id,task_run_id) ON DELETE CASCADE)"
                    )
                    cursor.execute(
                        "CREATE INDEX ronin_task_attempts_active_idx "
                        "ON ronin_task_attempts(workspace_id,state,lease_expires_at,"
                        "task_attempt_id)"
                    )
                    cursor.execute(
                        "CREATE INDEX ronin_task_attempts_task_idx "
                        "ON ronin_task_attempts(workspace_id,task_run_id,ordinal)"
                    )
                    cursor.execute(
                        "CREATE TABLE ronin_scheduler_resource_pools ("
                        "workspace_id TEXT NOT NULL REFERENCES ronin_workspaces(workspace_id) "
                        "ON DELETE CASCADE,pool_name TEXT NOT NULL,"
                        "capacity INTEGER NOT NULL CHECK (capacity >= 1),"
                        "created_at TEXT NOT NULL,updated_at TEXT NOT NULL,"
                        "row_version BIGINT NOT NULL DEFAULT 0,PRIMARY KEY(workspace_id,pool_name))"
                    )
                    cursor.execute(
                        "INSERT INTO ronin_scheduler_schema_migrations(version,applied_at) "
                        "VALUES (%s,%s)",
                        (
                            3,
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

    @staticmethod
    def _add_seconds(value: Instant, seconds: int) -> Instant:
        parsed = datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
        return Instant((parsed + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))

    def put_resource_pool(
        self,
        workspace_id: WorkspaceId,
        definition: ResourcePoolDefinition,
        *,
        now: Instant | str,
    ) -> ResourcePoolDefinition:
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_active_workspace(cursor, workspace_id)
                cursor.execute(
                    "INSERT INTO ronin_scheduler_resource_pools "
                    "(workspace_id,pool_name,capacity,created_at,updated_at) "
                    "VALUES (%s,%s,%s,%s,%s) ON CONFLICT(workspace_id,pool_name) DO UPDATE "
                    "SET capacity=EXCLUDED.capacity,updated_at=EXCLUDED.updated_at,"
                    "row_version=ronin_scheduler_resource_pools.row_version+1 "
                    "WHERE ronin_scheduler_resource_pools.capacity "
                    "IS DISTINCT FROM EXCLUDED.capacity",
                    (
                        str(workspace_id),
                        definition.name,
                        definition.capacity,
                        str(current),
                        str(current),
                    ),
                )
            connection.commit()
            return definition
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_resource_pool(
        self, workspace_id: WorkspaceId, pool_name: str
    ) -> ResourcePoolDefinition | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pool_name,capacity FROM ronin_scheduler_resource_pools "
                    "WHERE workspace_id=%s AND pool_name=%s",
                    (str(workspace_id), pool_name),
                )
                row = cursor.fetchone()
            return (
                None
                if row is None
                else ResourcePoolDefinition(row["pool_name"], int(row["capacity"]))
            )
        finally:
            connection.close()

    def list_resource_pools(self, workspace_id: WorkspaceId) -> tuple[ResourcePoolDefinition, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pool_name,capacity FROM ronin_scheduler_resource_pools "
                    "WHERE workspace_id=%s ORDER BY pool_name",
                    (str(workspace_id),),
                )
                rows = cursor.fetchall()
            return tuple(
                ResourcePoolDefinition(row["pool_name"], int(row["capacity"])) for row in rows
            )
        finally:
            connection.close()

    def resource_pool_usage(self, workspace_id: WorkspaceId, pool_name: str) -> int:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) AS count FROM ronin_task_attempts "
                    "WHERE workspace_id=%s AND pool_name=%s AND state='running'",
                    (str(workspace_id), pool_name),
                )
                row = cursor.fetchone()
            if row is None:
                raise AssertionError("resource pool usage query returned no row")
            return int(row["count"])
        finally:
            connection.close()

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
    def _workflow_state(
        cursor: Any, workspace_id: WorkspaceId, run_id: WorkflowRunId
    ) -> WorkflowRun:
        cursor.execute(
            "SELECT run_json FROM ronin_workflow_runs WHERE workspace_id=%s "
            "AND workflow_run_id=%s FOR UPDATE",
            (str(workspace_id), str(run_id)),
        )
        row = cursor.fetchone()
        if row is None:
            raise KeyError(str(run_id))
        return WorkflowRun.from_json(row["run_json"])

    @staticmethod
    def _write_workflow_state(
        cursor: Any,
        workspace_id: WorkspaceId,
        run: WorkflowRun,
        state: WorkflowRunState,
        now: Instant,
    ) -> None:
        updated = replace(run, state=state)
        cursor.execute(
            "UPDATE ronin_workflow_runs SET state=%s,run_json=%s,updated_at=%s,"
            "row_version=row_version+1 WHERE workspace_id=%s AND workflow_run_id=%s",
            (state, updated.to_json(), str(now), str(workspace_id), str(run.id)),
        )

    @staticmethod
    def _mark_failure_or_retry(
        cursor: Any,
        workspace_id: WorkspaceId,
        run: WorkflowRun,
        *,
        task_run_id: TaskRunId,
        node_id: NodeId,
        attempt_ordinal: int,
        now: Instant,
    ) -> None:
        policy = run.workflow_snapshot.policy_for(node_id)
        if attempt_ordinal < policy.retry.max_attempts:
            multiplier = 2 ** (attempt_ordinal - 1) if policy.retry.exponential_backoff else 1
            next_eligible = PostgresSchedulerSnapshotStore._add_seconds(
                now, policy.retry.delay_seconds * multiplier
            )
            cursor.execute(
                "UPDATE ronin_task_runs SET state='retry_wait',next_eligible_at=%s,updated_at=%s,"
                "row_version=row_version+1 "
                "WHERE workspace_id=%s AND task_run_id=%s",
                (str(next_eligible), str(now), str(workspace_id), str(task_run_id)),
            )
            return
        cursor.execute(
            "UPDATE ronin_task_runs SET state='failed',next_eligible_at=NULL,updated_at=%s,"
            "row_version=row_version+1 "
            "WHERE workspace_id=%s AND task_run_id=%s",
            (str(now), str(workspace_id), str(task_run_id)),
        )
        PostgresSchedulerSnapshotStore._write_workflow_state(
            cursor, workspace_id, run, "failed", now
        )

    def _reclaim_expired_in_transaction(self, cursor: Any, *, now: Instant) -> int:
        cursor.execute(
            "SELECT workspace_id,task_attempt_id,task_run_id,ordinal FROM ronin_task_attempts "
            "WHERE state='running' AND lease_expires_at<=%s "
            "ORDER BY workspace_id,task_attempt_id FOR UPDATE SKIP LOCKED",
            (str(now),),
        )
        attempts = cursor.fetchall()
        reclaimed = 0
        for attempt in attempts:
            workspace_id = WorkspaceId(attempt["workspace_id"])
            cursor.execute(
                "SELECT workflow_run_id,node_id FROM ronin_task_runs "
                "WHERE workspace_id=%s AND task_run_id=%s FOR UPDATE",
                (str(workspace_id), attempt["task_run_id"]),
            )
            task = cursor.fetchone()
            if task is None:
                raise AssertionError("task attempt references missing task run")
            run = self._workflow_state(cursor, workspace_id, WorkflowRunId(task["workflow_run_id"]))
            cursor.execute(
                "UPDATE ronin_task_attempts SET state='lost',failure_code='lease_expired',"
                "updated_at=%s WHERE workspace_id=%s AND task_attempt_id=%s AND state='running'",
                (str(now), str(workspace_id), attempt["task_attempt_id"]),
            )
            self._mark_failure_or_retry(
                cursor,
                workspace_id,
                run,
                task_run_id=TaskRunId(attempt["task_run_id"]),
                node_id=NodeId(task["node_id"]),
                attempt_ordinal=int(attempt["ordinal"]),
                now=now,
            )
            reclaimed += 1
        return reclaimed

    def reclaim_expired(self, *, now: Instant | str) -> int:
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                reclaimed = self._reclaim_expired_in_transaction(cursor, now=current)
            connection.commit()
            return reclaimed
        except Exception:
            connection.rollback()
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
        expiry = self._add_seconds(current, lease_seconds)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._reclaim_expired_in_transaction(cursor, now=current)
                query = (
                    "SELECT t.workspace_id,t.task_run_id,t.workflow_run_id,t.node_id "
                    "FROM ronin_task_runs t JOIN ronin_workflow_runs w "
                    "ON w.workspace_id=t.workspace_id AND w.workflow_run_id=t.workflow_run_id "
                    "WHERE t.state IN ('pending','retry_wait') AND "
                    "(t.next_eligible_at IS NULL OR t.next_eligible_at<=%s) "
                    "AND w.state IN ('pending','running')"
                )
                params: list[object] = [str(current)]
                if workspace_id is not None:
                    query += " AND t.workspace_id=%s"
                    params.append(str(workspace_id))
                query += " ORDER BY w.created_at,w.workflow_run_id,t.created_at,t.task_run_id"
                cursor.execute(query, tuple(params))
                candidates = cursor.fetchall()
                for candidate in candidates:
                    task_workspace = WorkspaceId(candidate["workspace_id"])
                    cursor.execute(
                        "SELECT state,attempt_count,next_eligible_at FROM ronin_task_runs "
                        "WHERE workspace_id=%s AND task_run_id=%s FOR UPDATE SKIP LOCKED",
                        (str(task_workspace), candidate["task_run_id"]),
                    )
                    task = cursor.fetchone()
                    if (
                        task is None
                        or task["state"] not in {"pending", "retry_wait"}
                        or (
                            task["next_eligible_at"] is not None
                            and task["next_eligible_at"] > str(current)
                        )
                    ):
                        continue
                    run = self._workflow_state(
                        cursor, task_workspace, WorkflowRunId(candidate["workflow_run_id"])
                    )
                    if run.state not in {"pending", "running"}:
                        continue
                    node_id = NodeId(candidate["node_id"])
                    predecessors = self._predecessor_ids(run, node_id)
                    if predecessors:
                        cursor.execute(
                            "SELECT node_id,state FROM ronin_task_runs WHERE workspace_id=%s "
                            "AND workflow_run_id=%s AND node_id=ANY(%s)",
                            (str(task_workspace), str(run.id), list(predecessors)),
                        )
                        states = {row["node_id"]: row["state"] for row in cursor.fetchall()}
                        predecessor_states = tuple(states.get(item) for item in predecessors)
                        if any(
                            state in {"failed", "cancelled", "blocked"}
                            for state in predecessor_states
                        ):
                            cursor.execute(
                                "UPDATE ronin_task_runs SET state='blocked',updated_at=%s,"
                                "row_version=row_version+1 "
                                "WHERE workspace_id=%s AND task_run_id=%s",
                                (str(current), str(task_workspace), candidate["task_run_id"]),
                            )
                            continue
                        if any(state != "succeeded" for state in predecessor_states):
                            continue
                    max_concurrency = run.workflow_snapshot.max_concurrency
                    if max_concurrency is not None:
                        cursor.execute(
                            "SELECT COUNT(*) AS count FROM ronin_task_runs WHERE workspace_id=%s "
                            "AND workflow_run_id=%s AND state='running'",
                            (str(task_workspace), str(run.id)),
                        )
                        if int(cursor.fetchone()["count"]) >= max_concurrency:
                            continue
                    policy = run.workflow_snapshot.policy_for(node_id)
                    pool_name = policy.pool
                    if pool_name is not None:
                        cursor.execute(
                            "SELECT capacity FROM ronin_scheduler_resource_pools "
                            "WHERE workspace_id=%s AND pool_name=%s FOR UPDATE",
                            (str(task_workspace), pool_name),
                        )
                        pool = cursor.fetchone()
                        if pool is None:
                            continue
                        cursor.execute(
                            "SELECT COUNT(*) AS count FROM ronin_task_attempts "
                            "WHERE workspace_id=%s AND pool_name=%s AND state='running'",
                            (str(task_workspace), pool_name),
                        )
                        if int(cursor.fetchone()["count"]) >= int(pool["capacity"]):
                            continue
                    ordinal = int(task["attempt_count"]) + 1
                    if ordinal > policy.retry.max_attempts:
                        cursor.execute(
                            "UPDATE ronin_task_runs SET state='failed',updated_at=%s,"
                            "row_version=row_version+1 "
                            "WHERE workspace_id=%s AND task_run_id=%s",
                            (str(current), str(task_workspace), candidate["task_run_id"]),
                        )
                        self._write_workflow_state(cursor, task_workspace, run, "failed", current)
                        continue
                    cursor.execute(
                        "INSERT INTO ronin_task_attempts(workspace_id,task_attempt_id,task_run_id,"
                        "ordinal,state,lease_owner,lease_token,lease_expires_at,heartbeat_at,"
                        "failure_code,created_at,updated_at,pool_name) "
                        "VALUES (%s,%s,%s,%s,'running',%s,%s,%s,%s,NULL,%s,%s,%s)",
                        (
                            str(task_workspace),
                            str(attempt_id),
                            candidate["task_run_id"],
                            ordinal,
                            owner,
                            str(lease_token),
                            str(expiry),
                            str(current),
                            str(current),
                            str(current),
                            pool_name,
                        ),
                    )
                    cursor.execute(
                        "UPDATE ronin_task_runs SET state='running',attempt_count=%s,"
                        "next_eligible_at=NULL,updated_at=%s,row_version=row_version+1 "
                        "WHERE workspace_id=%s AND task_run_id=%s",
                        (ordinal, str(current), str(task_workspace), candidate["task_run_id"]),
                    )
                    if run.state == "pending":
                        self._write_workflow_state(cursor, task_workspace, run, "running", current)
                    connection.commit()
                    return ClaimedTask(
                        task_workspace,
                        run.id,
                        TaskRunId(candidate["task_run_id"]),
                        node_id,
                        attempt_id,
                        ordinal,
                        owner,
                        lease_token,
                        expiry,
                        pool_name,
                    )
            connection.commit()
            return None
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _active_attempt(
        self,
        cursor: Any,
        workspace_id: WorkspaceId,
        attempt_id: TaskAttemptId,
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant,
    ) -> Any:
        cursor.execute(
            "SELECT * FROM ronin_task_attempts WHERE workspace_id=%s AND task_attempt_id=%s "
            "AND state='running' AND lease_owner=%s AND lease_token=%s AND lease_expires_at>%s "
            "FOR UPDATE",
            (str(workspace_id), str(attempt_id), owner, str(lease_token), str(now)),
        )
        attempt = cursor.fetchone()
        if attempt is None:
            raise ValueError("task attempt lease ownership lost")
        return attempt

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
        expiry = self._add_seconds(current, lease_seconds)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._active_attempt(
                    cursor,
                    workspace_id,
                    attempt_id,
                    owner=owner,
                    lease_token=lease_token,
                    now=current,
                )
                cursor.execute(
                    "UPDATE ronin_task_attempts SET heartbeat_at=%s,lease_expires_at=%s,"
                    "updated_at=%s "
                    "WHERE workspace_id=%s AND task_attempt_id=%s",
                    (str(current), str(expiry), str(current), str(workspace_id), str(attempt_id)),
                )
            connection.commit()
            return expiry
        except Exception:
            connection.rollback()
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
            with connection.cursor() as cursor:
                attempt = self._active_attempt(
                    cursor,
                    workspace_id,
                    attempt_id,
                    owner=owner,
                    lease_token=lease_token,
                    now=current,
                )
                cursor.execute(
                    "SELECT workflow_run_id,node_id FROM ronin_task_runs "
                    "WHERE workspace_id=%s AND task_run_id=%s FOR UPDATE",
                    (str(workspace_id), attempt["task_run_id"]),
                )
                task = cursor.fetchone()
                if task is None:
                    raise AssertionError("task attempt references missing task run")
                run = self._workflow_state(
                    cursor, workspace_id, WorkflowRunId(task["workflow_run_id"])
                )
                attempt_state = "succeeded" if succeeded else "failed"
                cursor.execute(
                    "UPDATE ronin_task_attempts SET state=%s,failure_code=%s,updated_at=%s "
                    "WHERE workspace_id=%s AND task_attempt_id=%s",
                    (attempt_state, failure_code, str(current), str(workspace_id), str(attempt_id)),
                )
                if succeeded:
                    cursor.execute(
                        "UPDATE ronin_task_runs SET state='succeeded',next_eligible_at=NULL,"
                        "updated_at=%s,"
                        "row_version=row_version+1 "
                        "WHERE workspace_id=%s AND task_run_id=%s",
                        (str(current), str(workspace_id), attempt["task_run_id"]),
                    )
                    cursor.execute(
                        "SELECT COUNT(*) AS count FROM ronin_task_runs WHERE workspace_id=%s "
                        "AND workflow_run_id=%s AND state!='succeeded'",
                        (str(workspace_id), str(run.id)),
                    )
                    if int(cursor.fetchone()["count"]) == 0:
                        self._write_workflow_state(cursor, workspace_id, run, "succeeded", current)
                else:
                    self._mark_failure_or_retry(
                        cursor,
                        workspace_id,
                        run,
                        task_run_id=TaskRunId(attempt["task_run_id"]),
                        node_id=NodeId(task["node_id"]),
                        attempt_ordinal=int(attempt["ordinal"]),
                        now=current,
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
