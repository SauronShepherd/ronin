from __future__ import annotations

from pathlib import Path

import pytest
from studio_core import (
    Node,
    OperatorRef,
    Pipeline,
    ProjectId,
    ProjectManifest,
    RepositoryBinding,
    ExecutionProfile,
    RuntimeProfileRef,
    Trigger,
    WorkflowDefinition,
    WorkflowId,
    WorkflowRunId,
    Workspace,
    WorkspaceId,
)
from studio_execution.scheduler_bridge import (
    UnsupportedTaskExecution,
    plan_scheduler_execution,
)
from studio_orchestrator import LeaseToken
from studio_storage.scheduler_execution import SchedulerExecutionLinkStore
from studio_storage.scheduler_fencing import TaskAttemptId
from studio_storage.workspaces import SqliteWorkspaceStore

NOW = "2026-09-12T20:00:00.000000Z"


def _manifest() -> ProjectManifest:
    from studio_core import Project

    return ProjectManifest.from_project(
        Project(
            ProjectId("project-1"),
            "Project",
            (RepositoryBinding("code", "https://git.example.test/repo.git", role="primary"),),
            ExecutionProfile(runtime=RuntimeProfileRef("python", "3.11")),
        )
    )


def _workflow(operator: str = "notebook.run") -> WorkflowDefinition:
    node = Node.create(
        operator=OperatorRef(operator),
        instance_key="task-1",
        params={"target": "notebooks/example.ronin.json", "parameters": {"limit": 10}},
    )
    return WorkflowDefinition(WorkflowId("workflow-1"), "Workflow", Pipeline((node,)))


def _claimed(tmp_path: Path, operator: str = "notebook.run"):
    database = tmp_path / "ronin.db"
    workspace_id = WorkspaceId("workspace-1")
    workspace_store = SqliteWorkspaceStore(database, migration_now=NOW)
    workspace_store.create_workspace(Workspace(workspace_id, "Workspace"), now=NOW)
    workspace_store.register_project(workspace_id, _manifest(), now=NOW)

    store = SchedulerExecutionLinkStore(database, migration_now=NOW)
    workflow = _workflow(operator)
    store.put_workflow(workspace_id, workflow, now=NOW)
    run = store.create_run(
        workspace_id,
        WorkflowRunId("workflow-run-1"),
        workflow.id,
        Trigger("manual", "trigger-1"),
        now=NOW,
    )
    claim = store.claim_next_task(
        owner="scheduler-controller",
        lease_token=LeaseToken("task-lease-1"),
        attempt_id=TaskAttemptId("task-attempt-1"),
        lease_seconds=60,
        now=NOW,
        workspace_id=workspace_id,
    )
    assert claim is not None
    return store, workspace_id, run, claim


def test_scheduler_execution_plan_is_deterministic_and_uses_existing_job_contract(
    tmp_path: Path,
) -> None:
    _store, _workspace_id, run, claim = _claimed(tmp_path)
    first = plan_scheduler_execution(claim, run, "project-1", now=NOW)
    second = plan_scheduler_execution(claim, run, "project-1", now=NOW)

    assert first.job == second.job
    assert first.run == second.run
    assert first.job.target == "notebooks/example.ronin.json"
    assert first.job.parameters_json == '{"limit":10}'
    assert first.job.idempotency_key == "scheduler:task-attempt-1"
    assert first.run.job_id == first.job.id


def test_execution_link_requires_live_scheduler_lease_and_is_idempotent(tmp_path: Path) -> None:
    store, workspace_id, run, claim = _claimed(tmp_path)
    plan = plan_scheduler_execution(claim, run, "project-1", now=NOW)

    first = store.bind_execution(
        workspace_id,
        claim.attempt_id,
        job_id=plan.job.id,
        request_digest=plan.job.request_digest,
        owner=claim.lease_owner,
        lease_token=claim.lease_token,
        now=NOW,
    )
    second = store.bind_execution(
        workspace_id,
        claim.attempt_id,
        job_id=plan.job.id,
        request_digest=plan.job.request_digest,
        owner=claim.lease_owner,
        lease_token=claim.lease_token,
        now=NOW,
    )
    assert first == second
    assert store.get_execution_link(workspace_id, claim.attempt_id) == first

    with pytest.raises(ValueError, match="lease ownership lost"):
        store.bind_execution(
            workspace_id,
            claim.attempt_id,
            job_id=plan.job.id,
            request_digest=plan.job.request_digest,
            owner="stale-controller",
            lease_token=LeaseToken("wrong-token"),
            now=NOW,
        )


def test_unsupported_operator_fails_without_fabricating_execution(tmp_path: Path) -> None:
    _store, _workspace_id, run, claim = _claimed(tmp_path, "source.table")
    with pytest.raises(UnsupportedTaskExecution, match="source.table@1"):
        plan_scheduler_execution(claim, run, "project-1", now=NOW)
