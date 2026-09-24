from __future__ import annotations

import json
from pathlib import Path

import pytest
from studio_core import (
    ExecutionProfile,
    Node,
    OperatorRef,
    Pipeline,
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


def _workflow(
    operator: str = "notebook.run", *, params: dict[str, object] | None = None
) -> WorkflowDefinition:
    node = Node.create(
        operator=OperatorRef(operator),
        instance_key="task-1",
        params=params or {"target": "notebooks/example.ronin.json", "parameters": {"limit": 10}},
    )
    return WorkflowDefinition(WorkflowId("workflow-1"), "Workflow", Pipeline((node,)))


def _claimed(
    tmp_path: Path,
    operator: str = "notebook.run",
    *,
    params: dict[str, object] | None = None,
):
    database = tmp_path / "ronin.db"
    workspace_id = WorkspaceId("workspace-1")
    workspace_store = SqliteWorkspaceStore(database, migration_now=NOW)
    workspace_store.create_workspace(Workspace(workspace_id, "Workspace"), now=NOW)
    workspace_store.register_project(workspace_id, _manifest(), now=NOW)

    store = SchedulerExecutionLinkStore(database, migration_now=NOW)
    workflow = _workflow(operator, params=params)
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


def test_adapter_controls_are_carried_into_the_durable_job(tmp_path: Path) -> None:
    _store, _workspace_id, run, claim = _claimed(
        tmp_path,
        params={
            "target": "notebooks/example.ronin.json",
            "parameters": {"limit": 10},
            "resource_policy": {"cpu_millis": 500, "memory_bytes": 1048576},
            "evidence_ref": "artifact://evidence/run-1",
            "timeout_seconds": 600,
        },
    )
    plan = plan_scheduler_execution(claim, run, "project-1", now=NOW)
    payload = json.loads(plan.job.parameters_json)
    assert payload["resource_policy"] == {"cpu_millis": 500, "memory_bytes": 1048576}
    assert payload["evidence_ref"] == "artifact://evidence/run-1"
    assert payload["timeout_seconds"] == 600


@pytest.mark.parametrize(
    "controls",
    [
        {"resource_policy": []},
        {"resource_policy": "invalid"},
        {"evidence_ref": ""},
        {"evidence_ref": 42},
        {"timeout_seconds": 0},
        {"timeout_seconds": 604801},
        {"timeout_seconds": True},
    ],
)
def test_adapter_controls_fail_closed(tmp_path: Path, controls: dict[str, object]) -> None:
    _store, _workspace_id, run, claim = _claimed(
        tmp_path,
        params={
            "target": "notebooks/example.ronin.json",
            "parameters": {},
            **controls,
        },
    )
    with pytest.raises(ValueError, match="resource_policy|evidence_ref|timeout_seconds"):
        plan_scheduler_execution(claim, run, "project-1", now=NOW)


@pytest.mark.parametrize(
    ("operator", "params", "target", "parameters"),
    [
        (
            "sql.query",
            {"source": "SELECT 1", "parameters": {"limit": 10}},
            "sql.query",
            {"query": "SELECT 1", "parameters": {"limit": 10}},
        ),
        (
            "code.python",
            {"source": "return 1"},
            "return 1",
            {"source": "return 1"},
        ),
        (
            "data-engineering.pipeline-run",
            {"revision_key": "pipeline:1", "ir_digest": "a" * 64, "runtime": "local"},
            "data-engineering.pipeline-run.v1",
            {
                "revision_key": "pipeline:1",
                "ir_digest": "a" * 64,
                "runtime": "local",
                "parameters": {},
            },
        ),
        (
            "quality.gate",
            {
                "asset_id": "orders",
                "version": "v1",
                "contract_digest": "b" * 64,
                "rows_ref": "artifact://rows/orders",
            },
            "quality.gate.v1",
            {
                "asset_id": "orders",
                "version": "v1",
                "contract_digest": "b" * 64,
                "rows_ref": "artifact://rows/orders",
            },
        ),
        (
            "connector.sync",
            {
                "connector_id": "orders-api",
                "source_ref": "source://orders",
                "checkpoint_ref": "checkpoint://orders",
            },
            "connector.sync.v1",
            {
                "connector_id": "orders-api",
                "source_ref": "source://orders",
                "checkpoint_ref": "checkpoint://orders",
                "mode": "incremental",
            },
        ),
        (
            "graph.query",
            {"graph_id": "orders-graph", "query": "SELECT o FROM Order o", "limit": 25},
            "graph.query.v1",
            {"graph_id": "orders-graph", "query": "SELECT o FROM Order o", "limit": 25},
        ),
        (
            "notification.send",
            {
                "notification_id": "alert-1",
                "channel": "webhook",
                "destination_ref": "secret://alerts/webhook",
                "payload_ref": "artifact://payload/alert-1",
            },
            "notification.send.v1",
            {
                "notification_id": "alert-1",
                "channel": "webhook",
                "destination_ref": "secret://alerts/webhook",
                "payload_ref": "artifact://payload/alert-1",
            },
        ),
        (
            "semantic.refresh",
            {"model_id": "sales", "definition_digest": "c" * 64, "tile_limit": 20},
            "semantic.refresh.v1",
            {"model_id": "sales", "definition_digest": "c" * 64, "tile_limit": 20},
        ),
        (
            "ml.run",
            {
                "lab_id": "churn",
                "pipeline_digest": "d" * 64,
                "dataset_ref": "artifact://datasets/churn",
            },
            "ml.run.v1",
            {
                "lab_id": "churn",
                "pipeline_digest": "d" * 64,
                "dataset_ref": "artifact://datasets/churn",
            },
        ),
        (
            "genai.run",
            {
                "provider_id": "openai-compatible",
                "model_id": "demo",
                "prompt_ref": "artifact://prompts/demo",
            },
            "genai.run.v1",
            {
                "provider_id": "openai-compatible",
                "model_id": "demo",
                "prompt_ref": "artifact://prompts/demo",
                "max_tokens": 1024,
            },
        ),
    ],
)
def test_supported_migrated_operator_plans_a_durable_job(
    tmp_path: Path,
    operator: str,
    params: dict[str, object],
    target: str,
    parameters: dict[str, object],
) -> None:
    database = tmp_path / f"{operator.replace('.', '-')}.db"
    workspace_id = WorkspaceId("workspace-1")
    workspace_store = SqliteWorkspaceStore(database, migration_now=NOW)
    workspace_store.create_workspace(Workspace(workspace_id, "Workspace"), now=NOW)
    workspace_store.register_project(workspace_id, _manifest(), now=NOW)
    store = SchedulerExecutionLinkStore(database, migration_now=NOW)
    workflow = WorkflowDefinition(
        WorkflowId("workflow-1"),
        "Workflow",
        Pipeline(
            (Node.create(operator=OperatorRef(operator), instance_key="task-1", params=params),)
        ),
    )
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
    plan = plan_scheduler_execution(claim, run, "project-1", now=NOW)
    assert plan.job.target == target
    assert plan.job.parameters_json == json.dumps(parameters, sort_keys=True, separators=(",", ":"))
