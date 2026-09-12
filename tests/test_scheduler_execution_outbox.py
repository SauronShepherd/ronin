from __future__ import annotations

import asyncio
from dataclasses import replace
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
from studio_execution.scheduler_dispatch import dispatch_execution_intent
from studio_orchestrator import Instant, JobState, LeaseToken
from studio_storage import InMemoryJobStore
from studio_storage.scheduler_execution import SchedulerExecutionLinkStore
from studio_storage.scheduler_fencing import TaskAttemptId
from studio_storage.workspaces import SqliteWorkspaceStore

NOW = "2026-09-12T20:00:00.000000Z"
LATER = "2026-09-12T20:02:00.000000Z"


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
        params={"target": "notebooks/demo.ronin.json", "parameters": {"limit": 5}},
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
    claim = store.claim_next_task(
        owner="controller-1",
        lease_token=LeaseToken("lease-1"),
        attempt_id=TaskAttemptId("attempt-1"),
        lease_seconds=30,
        now=NOW,
        workspace_id=workspace_id,
    )
    assert claim is not None
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
    return store, workspace_id, run, claim, intent


def test_execution_intent_survives_controller_lease_expiry_without_duplicate_reclaim(
    tmp_path: Path,
) -> None:
    store, workspace_id, _run, _claim, intent = _setup(tmp_path)

    assert store.reclaim_expired(now=LATER) == 0
    assert store.get_execution_intent(workspace_id, intent.task_attempt_id) == intent
    assert (
        store.claim_next_task(
            owner="controller-2",
            lease_token=LeaseToken("lease-2"),
            attempt_id=TaskAttemptId("attempt-2"),
            lease_seconds=30,
            now=LATER,
            workspace_id=workspace_id,
        )
        is None
    )


def test_outbox_dispatch_is_idempotent_against_existing_job_store(tmp_path: Path) -> None:
    _store, _workspace_id, _run, _claim, intent = _setup(tmp_path)

    async def scenario() -> None:
        service = DurableExecutionService(InMemoryJobStore())
        try:
            first = await dispatch_execution_intent(intent, service)
            second = await dispatch_execution_intent(intent, service)
            assert first.id == intent.job.id
            assert second == first
            assert await service.status(intent.job.id) == first
        finally:
            await service.aclose()

    asyncio.run(scenario())


def test_terminal_success_reconciles_task_and_workflow_after_controller_loss(
    tmp_path: Path,
) -> None:
    store, workspace_id, run, claim, intent = _setup(tmp_path)
    terminal = replace(
        intent.job,
        state=JobState.SUCCEEDED,
        updated_at=Instant(LATER),
    )

    assert store.reconcile_execution(workspace_id, claim.attempt_id, terminal, now=LATER)
    task_runs = store.list_task_runs(workspace_id, run.id)
    assert len(task_runs) == 1
    assert task_runs[0].state == "succeeded"
    stored_run = store.get_run(workspace_id, run.id)
    assert stored_run is not None
    assert stored_run.state == "succeeded"
