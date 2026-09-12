from __future__ import annotations

import asyncio
from pathlib import Path

from studio_core import (
    EnvironmentDefinition,
    EnvironmentId,
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
from studio_core.scheduler_deployment import WorkflowDeploymentBinding
from studio_execution import DurableExecutionService
from studio_execution.scheduler_controller import SchedulerController
from studio_orchestrator import LeaseToken
from studio_storage import InMemoryJobStore
from studio_storage.environments import SqliteEnvironmentStore
from studio_storage.scheduler_controller import SchedulerControllerStore
from studio_storage.scheduler_fencing import TaskAttemptId
from studio_storage.workspaces import SqliteWorkspaceStore

NOW = "2026-09-12T20:00:00.000000Z"


def _manifest() -> ProjectManifest:
    return ProjectManifest.from_project(
        Project(
            ProjectId("project-1"),
            "Project",
            (RepositoryBinding("code", "https://git.example.test/repo.git", role="primary"),),
            ExecutionProfile(runtime=RuntimeProfileRef("python", "3.11")),
        )
    )


def _workflow() -> WorkflowDefinition:
    node = Node.create(
        operator=OperatorRef("notebook.run"),
        instance_key="notebook-task",
        params={"target": "notebooks/demo.ronin.json", "parameters": {"limit": 5}},
    )
    return WorkflowDefinition(WorkflowId("workflow-1"), "Workflow", Pipeline((node,)))


def _stores(tmp_path: Path):
    database = tmp_path / "ronin.db"
    workspace_id = WorkspaceId("workspace-1")
    workspace_store = SqliteWorkspaceStore(database, migration_now=NOW)
    workspace_store.create_workspace(Workspace(workspace_id, "Workspace"), now=NOW)
    workspace_store.register_project(workspace_id, _manifest(), now=NOW)
    environment_store = SqliteEnvironmentStore(database, migration_now=NOW)
    environment = EnvironmentDefinition(EnvironmentId("local"), "Local")
    environment_store.put_environment(workspace_id, environment, now=NOW)
    controller_store = SchedulerControllerStore(database, migration_now=NOW)
    workflow = _workflow()
    controller_store.put_workflow(workspace_id, workflow, now=NOW)
    return workspace_id, environment_store, controller_store, workflow, environment


def test_workflow_deployment_is_external_to_workflow_identity(tmp_path: Path) -> None:
    workspace_id, _environment_store, store, workflow, environment = _stores(tmp_path)
    before = workflow.to_json()
    binding = WorkflowDeploymentBinding(workflow.id, ProjectId("project-1"), environment.id)

    store.put_workflow_deployment(workspace_id, binding, now=NOW)

    assert store.get_workflow_deployment(workspace_id, workflow.id) == binding
    assert store.get_runnable_workflow_deployment(workspace_id, workflow.id) == binding
    assert workflow.to_json() == before


def test_controller_claims_publishes_and_dispatches_deterministic_job(tmp_path: Path) -> None:
    workspace_id, _environment_store, store, workflow, environment = _stores(tmp_path)
    store.put_workflow_deployment(
        workspace_id,
        WorkflowDeploymentBinding(workflow.id, ProjectId("project-1"), environment.id),
        now=NOW,
    )
    run = store.create_run(
        workspace_id,
        WorkflowRunId("workflow-run-1"),
        workflow.id,
        Trigger("manual", "trigger-1"),
        now=NOW,
    )

    async def scenario() -> None:
        service = DurableExecutionService(InMemoryJobStore())
        controller = SchedulerController(store, service)
        try:
            intent = await controller.claim_and_publish(
                workspace_id=workspace_id,
                owner="controller-1",
                lease_token=LeaseToken("lease-1"),
                attempt_id=TaskAttemptId("attempt-1"),
                lease_seconds=60,
                now=NOW,
            )
            assert intent is not None
            assert intent.job.project_id == "project-1"
            assert intent.job.target == "notebooks/demo.ronin.json"
            assert await controller.dispatch_pending() == 1
            stored = await service.status(intent.job.id)
            assert stored is not None
            assert stored.request_digest == intent.job.request_digest
            assert store.get_run(workspace_id, run.id) is not None
        finally:
            await service.aclose()

    asyncio.run(scenario())


def test_controller_fails_claim_when_workflow_has_no_deployment(tmp_path: Path) -> None:
    workspace_id, _environment_store, store, workflow, _environment = _stores(tmp_path)
    run = store.create_run(
        workspace_id,
        WorkflowRunId("workflow-run-1"),
        workflow.id,
        Trigger("manual", "trigger-1"),
        now=NOW,
    )

    async def scenario() -> None:
        service = DurableExecutionService(InMemoryJobStore())
        controller = SchedulerController(store, service)
        try:
            published = await controller.claim_and_publish(
                workspace_id=workspace_id,
                owner="controller-1",
                lease_token=LeaseToken("lease-1"),
                attempt_id=TaskAttemptId("attempt-1"),
                lease_seconds=60,
                now=NOW,
            )
            assert published is None
            tasks = store.list_task_runs(workspace_id, run.id)
            assert len(tasks) == 1
            assert tasks[0].state == "failed"
        finally:
            await service.aclose()

    asyncio.run(scenario())


def test_controller_revalidates_disabled_environment_before_publish(tmp_path: Path) -> None:
    workspace_id, environment_store, store, workflow, environment = _stores(tmp_path)
    store.put_workflow_deployment(
        workspace_id,
        WorkflowDeploymentBinding(workflow.id, ProjectId("project-1"), environment.id),
        now=NOW,
    )
    run = store.create_run(
        workspace_id,
        WorkflowRunId("workflow-run-1"),
        workflow.id,
        Trigger("manual", "trigger-1"),
        now=NOW,
    )
    environment_store.put_environment(
        workspace_id,
        EnvironmentDefinition(environment.id, "Local", state="disabled"),
        now=NOW,
    )

    async def scenario() -> None:
        service = DurableExecutionService(InMemoryJobStore())
        controller = SchedulerController(store, service)
        try:
            published = await controller.claim_and_publish(
                workspace_id=workspace_id,
                owner="controller-1",
                lease_token=LeaseToken("lease-1"),
                attempt_id=TaskAttemptId("attempt-1"),
                lease_seconds=60,
                now=NOW,
            )
            assert published is None
            tasks = store.list_task_runs(workspace_id, run.id)
            assert tasks[0].state == "failed"
        finally:
            await service.aclose()

    asyncio.run(scenario())
