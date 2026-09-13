from __future__ import annotations

import asyncio
from pathlib import Path

from studio_core import (
    ExecutionProfile,
    Node,
    OperatorRef,
    Pipeline,
    Project,
    ProjectId,
    ProjectManifest,
    RepositoryBinding,
    RetryPolicy,
    RuntimeProfileRef,
    TaskPolicy,
    Trigger,
    WorkflowDefinition,
    WorkflowId,
    WorkflowRunId,
    Workspace,
    WorkspaceId,
)
from studio_execution import DurableExecutionService
from studio_execution.scheduler_bridge import plan_scheduler_execution
from studio_execution.scheduler_dispatch import dispatch_execution_intent
from studio_execution.scheduler_timeout import enforce_task_timeouts
from studio_orchestrator import Instant, JobState, LeaseToken
from studio_storage import InMemoryJobStore
from studio_storage.scheduler_controller import SchedulerControllerStore
from studio_storage.scheduler_fencing import TaskAttemptId
from studio_storage.workspaces import SqliteWorkspaceStore

NOW = "2026-09-13T06:00:00.000000Z"
BEFORE_TIMEOUT = "2026-09-13T06:00:04.000000Z"
AFTER_TIMEOUT = "2026-09-13T06:00:06.000000Z"


def _manifest() -> ProjectManifest:
    return ProjectManifest.from_project(
        Project(
            ProjectId("project-1"),
            "Project",
            (RepositoryBinding("code", "https://git.example.test/repo.git", role="primary"),),
            ExecutionProfile(runtime=RuntimeProfileRef("python", "3.11")),
        )
    )


def _setup(tmp_path: Path, *, max_attempts: int = 1):
    database = tmp_path / "ronin.db"
    workspace_id = WorkspaceId("workspace-1")
    workspace_store = SqliteWorkspaceStore(database, migration_now=NOW)
    workspace_store.create_workspace(Workspace(workspace_id, "Workspace"), now=NOW)
    workspace_store.register_project(workspace_id, _manifest(), now=NOW)

    node = Node.create(
        operator=OperatorRef("notebook.run"),
        instance_key="notebook-task",
        params={"target": "notebooks/demo.ronin.json", "parameters": {}},
    )
    workflow = WorkflowDefinition(
        WorkflowId("workflow-1"),
        "Workflow",
        Pipeline((node,)),
        (TaskPolicy(node.id, RetryPolicy(max_attempts=max_attempts), timeout_seconds=5),),
    )
    store = SchedulerControllerStore(database, migration_now=NOW)
    store.put_workflow(workspace_id, workflow, now=NOW)
    run = store.create_run(
        workspace_id,
        WorkflowRunId("workflow-run-1"),
        workflow.id,
        Trigger("manual", "trigger-1"),
        now=NOW,
    )
    claim = store.claim_next_task(
        owner="controller-1",
        lease_token=LeaseToken("lease-1"),
        attempt_id=TaskAttemptId("attempt-1"),
        lease_seconds=60,
        now=NOW,
        workspace_id=workspace_id,
    )
    assert claim is not None
    return store, workspace_id, run, claim


def test_timeout_is_not_requested_before_snapshot_deadline(tmp_path: Path) -> None:
    store, workspace_id, run, _claim = _setup(tmp_path)

    async def scenario() -> None:
        service = DurableExecutionService(InMemoryJobStore())
        try:
            result = await enforce_task_timeouts(
                store,
                service,
                now=Instant(BEFORE_TIMEOUT),
            )
            assert result.detected == 0
            assert result.finalized == 0
        finally:
            await service.aclose()

    asyncio.run(scenario())
    assert store.list_task_runs(workspace_id, run.id)[0].state == "running"


def test_timeout_without_submitted_job_fails_task_and_workflow(tmp_path: Path) -> None:
    store, workspace_id, run, _claim = _setup(tmp_path)

    async def scenario() -> None:
        service = DurableExecutionService(InMemoryJobStore())
        try:
            result = await enforce_task_timeouts(
                store,
                service,
                now=Instant(AFTER_TIMEOUT),
            )
            assert result.detected == 1
            assert result.cancellation_requests == 0
            assert result.finalized == 1
        finally:
            await service.aclose()

    asyncio.run(scenario())
    assert store.list_task_runs(workspace_id, run.id)[0].state == "failed"
    stored_run = store.get_run(workspace_id, run.id)
    assert stored_run is not None
    assert stored_run.state == "failed"


def test_timeout_cancels_linked_job_then_uses_scheduler_retry_policy(tmp_path: Path) -> None:
    store, workspace_id, run, claim = _setup(tmp_path, max_attempts=2)
    plan = plan_scheduler_execution(claim, run, "project-1", now=NOW)
    intent = store.put_execution_intent(
        workspace_id,
        claim.attempt_id,
        job=plan.job,
        run=plan.run,
        owner=claim.lease_owner,
        lease_token=claim.lease_token,
        now=NOW,
    )

    async def scenario() -> None:
        service = DurableExecutionService(InMemoryJobStore())
        try:
            await dispatch_execution_intent(intent, service)
            result = await enforce_task_timeouts(
                store,
                service,
                now=Instant(AFTER_TIMEOUT),
            )
            assert result.detected == 1
            assert result.cancellation_requests == 1
            assert result.finalized == 1
            cancelled = await service.status(intent.job.id)
            assert cancelled is not None
            assert cancelled.state is JobState.CANCELLED
        finally:
            await service.aclose()

    asyncio.run(scenario())

    task = store.list_task_runs(workspace_id, run.id)[0]
    assert task.state == "retry_wait"
    assert store.get_execution_intent(workspace_id, claim.attempt_id) is None
    retry = store.claim_next_task(
        owner="controller-2",
        lease_token=LeaseToken("lease-2"),
        attempt_id=TaskAttemptId("attempt-2"),
        lease_seconds=60,
        now=AFTER_TIMEOUT,
        workspace_id=workspace_id,
    )
    assert retry is not None
    assert retry.attempt_ordinal == 2
