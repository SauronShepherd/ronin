from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from studio_core import (
    ExecutionProfile,
    Node,
    OperatorRef,
    Pipeline,
    Project,
    ProjectId,
    ProjectManifest,
    RepositoryBinding,
    RuntimeProfileRef,
    Trigger,
    WorkflowDefinition,
    WorkflowId,
    WorkflowRunId,
    Workspace,
    WorkspaceId,
)
from studio_execution import DurableExecutionService
from studio_execution.scheduler_bridge import plan_scheduler_execution
from studio_execution.scheduler_cancellation import cancel_workflow_run
from studio_execution.scheduler_dispatch import (
    dispatch_execution_intent,
    reconcile_execution_intent,
)
from studio_execution.scheduler_http import WorkflowCancellationHTTPAdapter
from studio_orchestrator import Instant, JobId, JobState, LeaseToken
from studio_storage import InMemoryJobStore
from studio_storage.scheduler_cancellation import (
    cancel_unsubmitted_execution,
    execution_intent_dispatch_allowed,
    reconcile_cancelled_execution,
    request_workflow_cancellation,
)
from studio_storage.scheduler_execution import SchedulerExecutionLinkStore
from studio_storage.scheduler_fencing import TaskAttemptId
from studio_storage.workspaces import SqliteWorkspaceStore

NOW = "2026-09-13T05:00:00.000000Z"
LATER = "2026-09-13T05:01:00.000000Z"


@pytest.mark.parametrize("allowed", [True, False])
def test_dispatch_authority_helper_delegates_to_postgres_adapter(allowed: bool) -> None:
    class PostgresDispatchAdapter:
        def postgres_execution_intent_dispatch_allowed(self, intent: object) -> bool:
            assert intent is sentinel
            return allowed

    sentinel = object()
    assert execution_intent_dispatch_allowed(PostgresDispatchAdapter(), sentinel) is allowed


def test_cancellation_helpers_delegate_to_postgres_adapter() -> None:
    workspace_id = WorkspaceId("workspace-1")
    workflow_run_id = WorkflowRunId("workflow-run-1")
    job_id = JobId("job-1")
    attempt_id = TaskAttemptId("attempt-1")
    cancelled_job = SimpleNamespace(id=job_id, request_digest="digest", state=JobState.CANCELLED)

    class PostgresCancellationAdapter:
        def postgres_request_workflow_cancellation(self, workspace, run, *, now):
            assert (workspace, run, now) == (workspace_id, workflow_run_id, LATER)
            return (job_id,)

        def postgres_cancel_unsubmitted_execution(self, workspace, job, *, now):
            assert (workspace, job, now) == (workspace_id, job_id, LATER)
            return True

        def postgres_reconcile_cancelled_execution(self, workspace, attempt, job, *, now):
            assert (workspace, attempt, job, now) == (
                workspace_id,
                attempt_id,
                cancelled_job,
                LATER,
            )
            return True

    store = PostgresCancellationAdapter()
    assert request_workflow_cancellation(store, workspace_id, workflow_run_id, now=LATER) == (
        job_id,
    )
    assert cancel_unsubmitted_execution(store, workspace_id, job_id, now=LATER)
    assert reconcile_cancelled_execution(store, workspace_id, attempt_id, cancelled_job, now=LATER)


def _manifest() -> ProjectManifest:
    return ProjectManifest.from_project(
        Project(
            ProjectId("project-1"),
            "Project",
            (RepositoryBinding("code", "https://git.example.test/repo.git", role="primary"),),
            ExecutionProfile(runtime=RuntimeProfileRef("python", "3.11")),
        )
    )


def _setup(tmp_path: Path):
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
    workflow = WorkflowDefinition(WorkflowId("workflow-1"), "Workflow", Pipeline((node,)))
    store = SchedulerExecutionLinkStore(database, migration_now=NOW)
    store.put_workflow(workspace_id, workflow, now=NOW)
    run = store.create_run(
        workspace_id,
        WorkflowRunId("workflow-run-1"),
        workflow.id,
        Trigger("manual", "trigger-1"),
        now=NOW,
    )
    return store, workspace_id, run


def _claim(store: SchedulerExecutionLinkStore, workspace_id: WorkspaceId):
    claim = store.claim_next_task(
        owner="controller-1",
        lease_token=LeaseToken("lease-1"),
        attempt_id=TaskAttemptId("attempt-1"),
        lease_seconds=60,
        now=NOW,
        workspace_id=workspace_id,
    )
    assert claim is not None
    return claim


def _publish_intent(store, workspace_id, run):
    claim = _claim(store, workspace_id)
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
    return claim, intent


def test_pending_workflow_cancellation_terminalizes_without_job(tmp_path: Path) -> None:
    store, workspace_id, run = _setup(tmp_path)

    assert request_workflow_cancellation(store, workspace_id, run.id, now=LATER) == ()

    stored_run = store.get_run(workspace_id, run.id)
    assert stored_run is not None
    assert stored_run.state == "cancelled"
    task_runs = store.list_task_runs(workspace_id, run.id)
    assert len(task_runs) == 1
    assert task_runs[0].state == "cancelled"


def test_http_cancellation_adapter_runs_durable_workflow_cancellation(tmp_path: Path) -> None:
    store, workspace_id, run = _setup(tmp_path)
    service = DurableExecutionService(InMemoryJobStore())
    try:
        adapter = WorkflowCancellationHTTPAdapter(store, service)

        assert adapter.cancel_workflow_run(workspace_id, run.id) == 0
        stored_run = store.get_run(workspace_id, run.id)
        assert stored_run is not None
        assert stored_run.state == "cancelled"
    finally:
        asyncio.run(service.aclose())


def test_cancellation_fences_claimed_task_before_execution_intent(tmp_path: Path) -> None:
    store, workspace_id, run = _setup(tmp_path)
    claim = _claim(store, workspace_id)
    plan = plan_scheduler_execution(claim, run, "project-1", now=NOW)

    assert request_workflow_cancellation(store, workspace_id, run.id, now=LATER) == ()

    with pytest.raises(ValueError, match="lease ownership lost"):
        store.put_execution_intent(
            workspace_id,
            claim.attempt_id,
            job=plan.job,
            run=plan.run,
            owner=claim.lease_owner,
            lease_token=claim.lease_token,
            now=LATER,
        )


def test_published_but_unsubmitted_job_is_retired_without_dispatch(tmp_path: Path) -> None:
    store, workspace_id, run = _setup(tmp_path)
    claim, intent = _publish_intent(store, workspace_id, run)

    async def scenario() -> None:
        service = DurableExecutionService(InMemoryJobStore())
        try:
            assert (
                await cancel_workflow_run(
                    store,
                    service,
                    workspace_id,
                    run.id,
                    now=Instant(LATER),
                )
                == 0
            )
            assert await service.status(intent.job.id) is None
        finally:
            await service.aclose()

    asyncio.run(scenario())

    assert store.get_execution_intent(workspace_id, claim.attempt_id) is None
    stored_run = store.get_run(workspace_id, run.id)
    assert stored_run is not None
    assert stored_run.state == "cancelled"
    task_runs = store.list_task_runs(workspace_id, run.id)
    assert task_runs[0].state == "cancelled"


def test_linked_job_cancellation_reconciles_workflow_terminal_state(tmp_path: Path) -> None:
    store, workspace_id, run = _setup(tmp_path)
    _claim_record, intent = _publish_intent(store, workspace_id, run)

    async def scenario() -> None:
        service = DurableExecutionService(InMemoryJobStore())
        try:
            await dispatch_execution_intent(intent, service)
            assert (
                await cancel_workflow_run(
                    store,
                    service,
                    workspace_id,
                    run.id,
                    now=Instant(LATER),
                )
                == 1
            )
            cancelled = await service.status(intent.job.id)
            assert cancelled is not None
            assert cancelled.state is JobState.CANCELLED
            assert await reconcile_execution_intent(
                intent,
                service,
                store,
                now=Instant(LATER),
            )
        finally:
            await service.aclose()

    asyncio.run(scenario())

    stored_run = store.get_run(workspace_id, run.id)
    assert stored_run is not None
    assert stored_run.state == "cancelled"
    task_runs = store.list_task_runs(workspace_id, run.id)
    assert len(task_runs) == 1
    assert task_runs[0].state == "cancelled"
