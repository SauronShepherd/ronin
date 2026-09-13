"""Durable scheduler cancellation transitions over existing execution links."""

from __future__ import annotations

from studio_core import WorkflowRunId, WorkspaceId
from studio_orchestrator import Instant, Job, JobId, JobState

from .scheduler_execution import (
    SchedulerExecutionLinkStore,
    TaskExecutionIntent,
    TaskExecutionLinkConflict,
)
from .scheduler_fencing import TaskAttemptId


def _finish_workflow_if_cancelled(
    store: SchedulerExecutionLinkStore,
    connection,
    workspace_id: WorkspaceId,
    workflow_run_id: WorkflowRunId,
    *,
    now: Instant,
) -> None:
    remaining = connection.execute(
        "SELECT COUNT(*) AS count FROM task_runs WHERE workspace_id=? "
        "AND workflow_run_id=? AND state NOT IN ('succeeded','failed','cancelled')",
        (str(workspace_id), str(workflow_run_id)),
    ).fetchone()
    if remaining is None:
        raise AssertionError("workflow cancellation query returned no row")
    if int(remaining["count"]) != 0:
        return
    workflow = store._workflow_state(connection, workspace_id, workflow_run_id)
    if workflow.state == "cancelling":
        store._write_workflow_state(
            connection,
            workspace_id,
            workflow,
            state="cancelled",
            now=now,
        )


def execution_intent_dispatch_allowed(
    store: SchedulerExecutionLinkStore,
    intent: TaskExecutionIntent,
) -> bool:
    """Return whether an outbox intent still has live scheduler authority to dispatch."""

    connection = store._connect()
    try:
        row = connection.execute(
            "SELECT a.state AS attempt_state,t.state AS task_state,w.state AS workflow_state "
            "FROM task_execution_intents i "
            "JOIN task_attempts a ON a.workspace_id=i.workspace_id "
            "AND a.task_attempt_id=i.task_attempt_id "
            "JOIN task_runs t ON t.workspace_id=a.workspace_id "
            "AND t.task_run_id=a.task_run_id "
            "JOIN workflow_runs w ON w.workspace_id=t.workspace_id "
            "AND w.workflow_run_id=t.workflow_run_id "
            "WHERE i.workspace_id=? AND i.task_attempt_id=? AND i.job_id=?",
            (
                str(intent.workspace_id),
                str(intent.task_attempt_id),
                str(intent.job.id),
            ),
        ).fetchone()
        return row is not None and (
            row["attempt_state"] == "running"
            and row["task_state"] == "running"
            and row["workflow_state"] in {"pending", "running"}
        )
    finally:
        connection.close()


def request_workflow_cancellation(
    store: SchedulerExecutionLinkStore,
    workspace_id: WorkspaceId,
    workflow_run_id: WorkflowRunId,
    *,
    now: Instant | str,
) -> tuple[JobId, ...]:
    """Persist cancellation intent and return linked Jobs that may be in flight.

    Pending work is terminalized in the same transaction. A running task that has
    not published durable execution intent is cancelled immediately, which removes
    its scheduler write authority. Published execution intents remain attached until
    application code determines whether the corresponding Job exists.
    """

    current = Instant(now)
    connection = store._connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        workflow = store._workflow_state(connection, workspace_id, workflow_run_id)
        if workflow.state in {"succeeded", "failed", "cancelled"}:
            connection.execute("COMMIT")
            return ()
        if workflow.state != "cancelling":
            store._write_workflow_state(
                connection,
                workspace_id,
                workflow,
                state="cancelling",
                now=current,
            )

        task_rows = connection.execute(
            "SELECT * FROM task_runs WHERE workspace_id=? AND workflow_run_id=? "
            "ORDER BY task_run_id",
            (str(workspace_id), str(workflow_run_id)),
        ).fetchall()
        outstanding: list[JobId] = []
        for task in task_rows:
            state = task["state"]
            if state in {"succeeded", "failed", "cancelled"}:
                continue
            if state in {"pending", "retry_wait", "blocked"}:
                connection.execute(
                    "UPDATE task_runs SET state='cancelled',next_eligible_at=NULL,updated_at=?,"
                    "row_version=row_version+1 WHERE workspace_id=? AND task_run_id=?",
                    (current, str(workspace_id), task["task_run_id"]),
                )
                continue
            if state != "running":
                raise AssertionError(f"unsupported cancellable task state: {state}")

            attempt = connection.execute(
                "SELECT * FROM task_attempts WHERE workspace_id=? AND task_run_id=? "
                "AND state='running' ORDER BY ordinal DESC LIMIT 1",
                (str(workspace_id), task["task_run_id"]),
            ).fetchone()
            if attempt is None:
                raise AssertionError("running task has no running task attempt")
            intent = connection.execute(
                "SELECT job_id FROM task_execution_intents "
                "WHERE workspace_id=? AND task_attempt_id=?",
                (str(workspace_id), attempt["task_attempt_id"]),
            ).fetchone()
            if intent is None:
                connection.execute(
                    "UPDATE task_attempts SET state='cancelled',failure_code=NULL,updated_at=? "
                    "WHERE workspace_id=? AND task_attempt_id=? AND state='running'",
                    (current, str(workspace_id), attempt["task_attempt_id"]),
                )
                connection.execute(
                    "UPDATE task_runs SET state='cancelled',next_eligible_at=NULL,updated_at=?,"
                    "row_version=row_version+1 WHERE workspace_id=? AND task_run_id=?",
                    (current, str(workspace_id), task["task_run_id"]),
                )
                continue
            outstanding.append(JobId(intent["job_id"]))

        _finish_workflow_if_cancelled(
            store,
            connection,
            workspace_id,
            workflow_run_id,
            now=current,
        )
        connection.execute("COMMIT")
        return tuple(outstanding)
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def cancel_unsubmitted_execution(
    store: SchedulerExecutionLinkStore,
    workspace_id: WorkspaceId,
    job_id: JobId,
    *,
    now: Instant | str,
) -> bool:
    """Cancel a scheduler execution intent that never reached the durable JobStore."""

    current = Instant(now)
    connection = store._connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        intent = connection.execute(
            "SELECT * FROM task_execution_intents WHERE workspace_id=? AND job_id=?",
            (str(workspace_id), str(job_id)),
        ).fetchone()
        if intent is None:
            connection.execute("COMMIT")
            return False
        attempt = connection.execute(
            "SELECT * FROM task_attempts WHERE workspace_id=? AND task_attempt_id=?",
            (str(workspace_id), intent["task_attempt_id"]),
        ).fetchone()
        if attempt is None:
            raise AssertionError("execution intent references missing task attempt")
        task = connection.execute(
            "SELECT * FROM task_runs WHERE workspace_id=? AND task_run_id=?",
            (str(workspace_id), attempt["task_run_id"]),
        ).fetchone()
        if task is None:
            raise AssertionError("task attempt references missing task run")
        workflow_run_id = WorkflowRunId(task["workflow_run_id"])
        workflow = store._workflow_state(connection, workspace_id, workflow_run_id)
        if workflow.state not in {"cancelling", "cancelled"}:
            raise RuntimeError("cannot cancel unsubmitted execution without workflow cancellation")

        connection.execute(
            "UPDATE task_attempts SET state='cancelled',failure_code=NULL,updated_at=? "
            "WHERE workspace_id=? AND task_attempt_id=? AND state='running'",
            (current, str(workspace_id), intent["task_attempt_id"]),
        )
        connection.execute(
            "UPDATE task_runs SET state='cancelled',next_eligible_at=NULL,updated_at=?,"
            "row_version=row_version+1 WHERE workspace_id=? AND task_run_id=? "
            "AND state NOT IN ('succeeded','failed','cancelled')",
            (current, str(workspace_id), task["task_run_id"]),
        )
        connection.execute(
            "DELETE FROM task_execution_intents WHERE workspace_id=? AND task_attempt_id=?",
            (str(workspace_id), intent["task_attempt_id"]),
        )
        _finish_workflow_if_cancelled(
            store,
            connection,
            workspace_id,
            workflow_run_id,
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


def reconcile_cancelled_execution(
    store: SchedulerExecutionLinkStore,
    workspace_id: WorkspaceId,
    attempt_id: TaskAttemptId,
    job: Job,
    *,
    now: Instant | str,
) -> bool:
    """Project a terminal cancelled Job back into scheduler task/workflow state."""

    if job.state is not JobState.CANCELLED:
        return False
    current = Instant(now)
    connection = store._connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        intent = connection.execute(
            "SELECT job_id,request_digest FROM task_execution_intents "
            "WHERE workspace_id=? AND task_attempt_id=?",
            (str(workspace_id), str(attempt_id)),
        ).fetchone()
        if intent is None:
            return False
        if intent["job_id"] != str(job.id) or intent["request_digest"] != job.request_digest:
            raise TaskExecutionLinkConflict("cancelled job does not match execution intent")

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
        if task["state"] in {"succeeded", "failed", "cancelled"}:
            connection.execute("COMMIT")
            return True

        workflow_run_id = WorkflowRunId(task["workflow_run_id"])
        connection.execute(
            "UPDATE task_attempts SET state='cancelled',failure_code=NULL,updated_at=? "
            "WHERE workspace_id=? AND task_attempt_id=?",
            (current, str(workspace_id), str(attempt_id)),
        )
        connection.execute(
            "UPDATE task_runs SET state='cancelled',next_eligible_at=NULL,updated_at=?,"
            "row_version=row_version+1 WHERE workspace_id=? AND task_run_id=?",
            (current, str(workspace_id), task["task_run_id"]),
        )
        _finish_workflow_if_cancelled(
            store,
            connection,
            workspace_id,
            workflow_run_id,
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
    "cancel_unsubmitted_execution",
    "execution_intent_dispatch_allowed",
    "reconcile_cancelled_execution",
    "request_workflow_cancellation",
)
