"""Durable task-timeout detection and terminal scheduler projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from studio_core import NodeId, TaskRunId, WorkflowRunId, WorkspaceId
from studio_orchestrator import Instant, JobId

from .scheduler_controller import SchedulerControllerStore
from .scheduler_fencing import TaskAttemptId


@dataclass(frozen=True, slots=True)
class TaskTimeoutRequest:
    workspace_id: WorkspaceId
    task_attempt_id: TaskAttemptId
    job_id: JobId | None
    requested_at: Instant


def _add_seconds(value: Instant | str, seconds: int) -> Instant:
    parsed = datetime.strptime(
        str(Instant(value)), "%Y-%m-%dT%H:%M:%S.%fZ"
    ).replace(tzinfo=UTC)
    return Instant(
        (parsed + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )


def request_overdue_timeouts(
    store: SchedulerControllerStore,
    *,
    now: Instant | str,
    limit: int = 100,
) -> tuple[TaskTimeoutRequest, ...]:
    """Persist timeout intent for overdue running task attempts.

    The timeout decision is derived from the immutable WorkflowRun snapshot and the
    attempt's durable creation time. It is written before any Job cancellation call.
    """

    if not 1 <= limit <= 1000:
        raise ValueError("timeout request limit must be between 1 and 1000")
    current = Instant(now)
    connection = store._connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            "SELECT a.*,t.node_id,t.workflow_run_id,w.run_json,i.job_id "
            "FROM task_attempts a "
            "JOIN task_runs t ON t.workspace_id=a.workspace_id "
            "AND t.task_run_id=a.task_run_id "
            "JOIN workflow_runs w ON w.workspace_id=t.workspace_id "
            "AND w.workflow_run_id=t.workflow_run_id "
            "LEFT JOIN task_execution_intents i ON i.workspace_id=a.workspace_id "
            "AND i.task_attempt_id=a.task_attempt_id "
            "LEFT JOIN task_timeout_requests r ON r.workspace_id=a.workspace_id "
            "AND r.task_attempt_id=a.task_attempt_id "
            "WHERE a.state='running' AND t.state='running' AND w.state='running' "
            "AND r.task_attempt_id IS NULL "
            "ORDER BY a.created_at,a.task_attempt_id"
        ).fetchall()
        requested: list[TaskTimeoutRequest] = []
        for row in rows:
            run = store._workflow_state(
                connection,
                WorkspaceId(row["workspace_id"]),
                WorkflowRunId(row["workflow_run_id"]),
            )
            policy = run.workflow_snapshot.policy_for(NodeId(row["node_id"]))
            timeout_seconds = policy.timeout_seconds
            if timeout_seconds is None:
                continue
            if current < _add_seconds(Instant(row["created_at"]), timeout_seconds):
                continue
            request = TaskTimeoutRequest(
                WorkspaceId(row["workspace_id"]),
                TaskAttemptId(row["task_attempt_id"]),
                None if row["job_id"] is None else JobId(row["job_id"]),
                current,
            )
            connection.execute(
                "INSERT INTO task_timeout_requests("
                "workspace_id,task_attempt_id,job_id,requested_at) VALUES (?,?,?,?)",
                (
                    str(request.workspace_id),
                    str(request.task_attempt_id),
                    None if request.job_id is None else str(request.job_id),
                    request.requested_at,
                ),
            )
            requested.append(request)
            if len(requested) >= limit:
                break
        connection.execute("COMMIT")
        return tuple(requested)
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def list_timeout_requests(
    store: SchedulerControllerStore,
    *,
    limit: int = 100,
) -> tuple[TaskTimeoutRequest, ...]:
    if not 1 <= limit <= 1000:
        raise ValueError("timeout request limit must be between 1 and 1000")
    connection = store._connect()
    try:
        rows = connection.execute(
            "SELECT workspace_id,task_attempt_id,job_id,requested_at "
            "FROM task_timeout_requests ORDER BY requested_at,task_attempt_id LIMIT ?",
            (limit,),
        ).fetchall()
        return tuple(
            TaskTimeoutRequest(
                WorkspaceId(row["workspace_id"]),
                TaskAttemptId(row["task_attempt_id"]),
                None if row["job_id"] is None else JobId(row["job_id"]),
                Instant(row["requested_at"]),
            )
            for row in rows
        )
    finally:
        connection.close()


def timeout_requested(
    store: SchedulerControllerStore,
    workspace_id: WorkspaceId,
    attempt_id: TaskAttemptId,
) -> bool:
    connection = store._connect()
    try:
        row = connection.execute(
            "SELECT 1 FROM task_timeout_requests WHERE workspace_id=? AND task_attempt_id=?",
            (str(workspace_id), str(attempt_id)),
        ).fetchone()
        return row is not None
    finally:
        connection.close()


def clear_timeout_request(
    store: SchedulerControllerStore,
    workspace_id: WorkspaceId,
    attempt_id: TaskAttemptId,
) -> None:
    connection = store._connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "DELETE FROM task_timeout_requests WHERE workspace_id=? AND task_attempt_id=?",
            (str(workspace_id), str(attempt_id)),
        )
        connection.execute("COMMIT")
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def finalize_timed_out_attempt(
    store: SchedulerControllerStore,
    request: TaskTimeoutRequest,
    *,
    now: Instant | str,
) -> bool:
    """Finish one durable timeout as retry/failure, or cancellation if user-cancelled."""

    current = Instant(now)
    connection = store._connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        marker = connection.execute(
            "SELECT job_id FROM task_timeout_requests "
            "WHERE workspace_id=? AND task_attempt_id=?",
            (str(request.workspace_id), str(request.task_attempt_id)),
        ).fetchone()
        if marker is None:
            connection.execute("COMMIT")
            return False
        marker_job = None if marker["job_id"] is None else JobId(marker["job_id"])
        if marker_job != request.job_id:
            raise RuntimeError("timeout request job identity changed")

        attempt = connection.execute(
            "SELECT * FROM task_attempts WHERE workspace_id=? AND task_attempt_id=?",
            (str(request.workspace_id), str(request.task_attempt_id)),
        ).fetchone()
        if attempt is None:
            raise KeyError(str(request.task_attempt_id))
        task = connection.execute(
            "SELECT * FROM task_runs WHERE workspace_id=? AND task_run_id=?",
            (str(request.workspace_id), attempt["task_run_id"]),
        ).fetchone()
        if task is None:
            raise AssertionError("timeout attempt references missing task run")
        workflow = store._workflow_state(
            connection,
            request.workspace_id,
            WorkflowRunId(task["workflow_run_id"]),
        )

        if task["state"] not in {"succeeded", "failed", "cancelled"}:
            if workflow.state == "cancelling":
                connection.execute(
                    "UPDATE task_attempts SET state='cancelled',failure_code=NULL,updated_at=? "
                    "WHERE workspace_id=? AND task_attempt_id=?",
                    (current, str(request.workspace_id), str(request.task_attempt_id)),
                )
                connection.execute(
                    "UPDATE task_runs SET state='cancelled',next_eligible_at=NULL,updated_at=?,"
                    "row_version=row_version+1 WHERE workspace_id=? AND task_run_id=?",
                    (current, str(request.workspace_id), task["task_run_id"]),
                )
                remaining = connection.execute(
                    "SELECT COUNT(*) AS count FROM task_runs WHERE workspace_id=? "
                    "AND workflow_run_id=? AND state NOT IN ('succeeded','failed','cancelled')",
                    (str(request.workspace_id), str(workflow.id)),
                ).fetchone()
                if remaining is None:
                    raise AssertionError("workflow cancellation query returned no row")
                if int(remaining["count"]) == 0:
                    store._write_workflow_state(
                        connection,
                        request.workspace_id,
                        workflow,
                        state="cancelled",
                        now=current,
                    )
            else:
                connection.execute(
                    "UPDATE task_attempts SET state='failed',failure_code='timeout',updated_at=? "
                    "WHERE workspace_id=? AND task_attempt_id=?",
                    (current, str(request.workspace_id), str(request.task_attempt_id)),
                )
                store._mark_failure_or_retry(
                    connection,
                    request.workspace_id,
                    workflow,
                    task_run_id=TaskRunId(task["task_run_id"]),
                    node_id=NodeId(task["node_id"]),
                    attempt_ordinal=int(attempt["ordinal"]),
                    now=current,
                )

        connection.execute(
            "DELETE FROM task_execution_intents "
            "WHERE workspace_id=? AND task_attempt_id=?",
            (str(request.workspace_id), str(request.task_attempt_id)),
        )
        connection.execute(
            "DELETE FROM task_timeout_requests WHERE workspace_id=? AND task_attempt_id=?",
            (str(request.workspace_id), str(request.task_attempt_id)),
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
    "TaskTimeoutRequest",
    "clear_timeout_request",
    "finalize_timed_out_attempt",
    "list_timeout_requests",
    "request_overdue_timeouts",
    "timeout_requested",
)
