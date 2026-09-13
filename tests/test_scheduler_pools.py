from __future__ import annotations

from pathlib import Path

from studio_core import (
    Node,
    OperatorRef,
    Pipeline,
    ResourcePoolDefinition,
    TaskPolicy,
    Trigger,
    WorkflowDefinition,
    WorkflowId,
    WorkflowRunId,
    Workspace,
    WorkspaceId,
)
from studio_execution.scheduler_bridge import plan_scheduler_execution
from studio_orchestrator import Instant, LeaseToken
from studio_storage.scheduler_execution import SchedulerExecutionLinkStore
from studio_storage.scheduler_fencing import FencedSqliteSchedulerStore, TaskAttemptId
from studio_storage.workspaces import SqliteWorkspaceStore

_T0 = Instant("2026-09-13T08:00:00.000000Z")
_T10 = Instant("2026-09-13T08:00:10.000000Z")
_T31 = Instant("2026-09-13T08:00:31.000000Z")
_WS = WorkspaceId("workspace-1")


def _store(
    tmp_path: Path,
) -> tuple[FencedSqliteSchedulerStore, WorkflowDefinition, Path]:
    path = tmp_path / "ronin.sqlite3"
    workspaces = SqliteWorkspaceStore(path, migration_now=_T0)
    workspaces.create_workspace(Workspace(_WS, "Workspace"), now=_T0)
    node = Node.create(
        operator=OperatorRef("notebook.run"),
        instance_key="task",
        params={"target": "notebooks/demo.ronin.json", "parameters": {}},
    )
    workflow = WorkflowDefinition(
        WorkflowId("workflow-1"),
        "Workflow",
        Pipeline((node,)),
        (TaskPolicy(node.id, pool="gpu"),),
    )
    store = FencedSqliteSchedulerStore(path, migration_now=_T0)
    store.put_workflow(_WS, workflow, now=_T0)
    store.create_run(
        _WS,
        WorkflowRunId("run-1"),
        workflow.id,
        Trigger("manual", "trigger-1"),
        now=_T0,
    )
    store.create_run(
        _WS,
        WorkflowRunId("run-2"),
        workflow.id,
        Trigger("manual", "trigger-2"),
        now=_T0,
    )
    return store, workflow, path


def test_named_pool_fails_closed_until_workspace_capacity_exists(tmp_path: Path) -> None:
    store, _workflow, _path = _store(tmp_path)

    assert (
        store.claim_next_task(
            owner="worker-1",
            lease_token=LeaseToken("lease-1"),
            attempt_id=TaskAttemptId("attempt-1"),
            lease_seconds=30,
            now=_T0,
            workspace_id=_WS,
        )
        is None
    )

    pool = ResourcePoolDefinition("gpu", 1)
    assert store.put_resource_pool(_WS, pool, now=_T0) == pool
    assert store.get_resource_pool(_WS, "gpu") == pool
    assert store.list_resource_pools(_WS) == (pool,)


def test_pool_capacity_is_reserved_with_task_claim_and_released_on_completion(
    tmp_path: Path,
) -> None:
    store, _workflow, _path = _store(tmp_path)
    store.put_resource_pool(_WS, ResourcePoolDefinition("gpu", 1), now=_T0)

    first = store.claim_next_task(
        owner="worker-1",
        lease_token=LeaseToken("lease-1"),
        attempt_id=TaskAttemptId("attempt-1"),
        lease_seconds=30,
        now=_T0,
        workspace_id=_WS,
    )
    assert first is not None
    assert first.pool_name == "gpu"
    assert store.resource_pool_usage(_WS, "gpu") == 1

    blocked = store.claim_next_task(
        owner="worker-2",
        lease_token=LeaseToken("lease-2"),
        attempt_id=TaskAttemptId("attempt-2"),
        lease_seconds=30,
        now=_T10,
        workspace_id=_WS,
    )
    assert blocked is None

    store.complete_task(
        _WS,
        first.attempt_id,
        owner=first.lease_owner,
        lease_token=first.lease_token,
        succeeded=True,
        failure_code=None,
        now=_T10,
    )
    assert store.resource_pool_usage(_WS, "gpu") == 0

    second = store.claim_next_task(
        owner="worker-2",
        lease_token=LeaseToken("lease-2"),
        attempt_id=TaskAttemptId("attempt-2"),
        lease_seconds=30,
        now=_T10,
        workspace_id=_WS,
    )
    assert second is not None
    assert second.workflow_run_id == WorkflowRunId("run-2")
    assert second.pool_name == "gpu"


def test_expired_pool_slot_is_reclaimed_before_next_claim(tmp_path: Path) -> None:
    store, _workflow, _path = _store(tmp_path)
    store.put_resource_pool(_WS, ResourcePoolDefinition("gpu", 1), now=_T0)

    first = store.claim_next_task(
        owner="worker-1",
        lease_token=LeaseToken("lease-1"),
        attempt_id=TaskAttemptId("attempt-1"),
        lease_seconds=30,
        now=_T0,
        workspace_id=_WS,
    )
    assert first is not None

    second = store.claim_next_task(
        owner="worker-2",
        lease_token=LeaseToken("lease-2"),
        attempt_id=TaskAttemptId("attempt-2"),
        lease_seconds=30,
        now=_T31,
        workspace_id=_WS,
    )
    assert second is not None
    assert second.workflow_run_id == WorkflowRunId("run-2")
    assert second.pool_name == "gpu"
    assert store.resource_pool_usage(_WS, "gpu") == 1


def test_execution_linked_attempt_keeps_pool_slot_after_lease_timestamp(tmp_path: Path) -> None:
    base_store, _workflow, path = _store(tmp_path)
    base_store.put_resource_pool(_WS, ResourcePoolDefinition("gpu", 1), now=_T0)
    store = SchedulerExecutionLinkStore(path, migration_now=_T0)

    first = store.claim_next_task(
        owner="controller-1",
        lease_token=LeaseToken("lease-1"),
        attempt_id=TaskAttemptId("attempt-1"),
        lease_seconds=30,
        now=_T0,
        workspace_id=_WS,
    )
    assert first is not None
    workflow_run = store.get_run(_WS, first.workflow_run_id)
    assert workflow_run is not None
    plan = plan_scheduler_execution(first, workflow_run, "project-1", now=_T0)
    store.put_execution_intent(
        _WS,
        first.attempt_id,
        job=plan.job,
        run=plan.run,
        owner=first.lease_owner,
        lease_token=first.lease_token,
        now=_T0,
    )

    assert store.resource_pool_usage(_WS, "gpu") == 1
    assert (
        store.claim_next_task(
            owner="controller-2",
            lease_token=LeaseToken("lease-2"),
            attempt_id=TaskAttemptId("attempt-2"),
            lease_seconds=30,
            now=_T31,
            workspace_id=_WS,
        )
        is None
    )
    assert store.resource_pool_usage(_WS, "gpu") == 1
