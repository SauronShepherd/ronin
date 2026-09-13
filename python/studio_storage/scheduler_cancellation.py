"""Durable scheduler cancellation transitions over existing execution links."""

from __future__ import annotations

from studio_core import WorkflowRunId, WorkspaceId
from studio_orchestrator import Instant, Job, JobId, JobState

from .scheduler_execution import SchedulerExecutionLinkStore, TaskExecutionLinkConflict
from .scheduler_fencing import TaskAttemptId


def request_workflow_cancellation(
    store: SchedulerExecutionLinkStore,
    workspace_id: WorkspaceId,
    workflow_run_id: WorkflowRunId,
    *,
    now: Instant | str,
) -> tuple[JobId, ...]:
    """Persist cancellation intent and return linked Jobs that still need cancellation.

    Pending work is terminalized in the same transaction. Running task attempts that
    have not yet published execution intent are cancelled and therefore lose their
    write fence. Attempts with durable execution intent stay running until the linked
    Job reaches ``cancelled``; callers can safely repeat this function after a crash
    to obtain the same outstanding Job identities.
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
            workflow = store._workflow_state(connection, workspace_id, workflow_run_id)

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

        remaining = connection.execute(
            "SELECT COUNT(*) AS count FROM task_runs WHERE workspace_id=? "
            "AND workflow_run_id=? AND state NOT IN ('succeeded','failed','cancelled')",
            (str(workspace_id), str(workflow_run_id)),
        ).fetchone()
        if remaining is None:
            raise AssertionError("workflow cancellation query returned no row")
        if int(remaining["count"]) == 0:
            store._write_workflow_state(
                connection,
                workspace_id,
                workflow,
                state="cancelled",
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
            raise KeyError(f"execution intent does not exist: {workspace_id}/{attempt_id}")
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
        if task["state"] == "cancelled":
            connection.execute("COMMIT")
            return True
        if task["state"] in {"succeeded", "failed"}:
            connection.execute("COMMIT")
            return True

        workflow = store._workflow_state(
            connection,
            workspace_id,
            WorkflowRunId(task["workflow_run_id"]),
        )
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
        remaining = connection.execute(
            "SELECT COUNT(*) AS count FROM task_runs WHERE workspace_id=? "
            "AND workflow_run_id=? AND state NOT IN ('succeeded','failed','cancelled')",
            (str(workspace_id), str(workflow.id)),
        ).fetchone()
        if remaining is None:
            raise AssertionError("workflow cancellation reconciliation returned no row")
        if workflow.state == "cancelling" and int(remaining["count"]) == 0:
            store._write_workflow_state(
                connection,
                workspace_id,
                workflow,
                state="cancelled",
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


__all__ = ("reconcile_cancelled_execution", "request_workflow_cancellation")
