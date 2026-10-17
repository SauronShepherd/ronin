from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from studio_core import (
    Node,
    NodeId,
    OperatorRef,
    Pipeline,
    ResourcePoolDefinition,
    RetryPolicy,
    Schedule,
    ScheduleId,
    TaskPolicy,
    Trigger,
    WorkflowDefinition,
    WorkflowId,
    WorkflowRunId,
    Workspace,
    WorkspaceId,
)
from studio_orchestrator import Instant, LeaseToken
from studio_storage import (
    PostgresMetadataStore,
    PostgresSchedulerLeadershipStore,
    PostgresSchedulerSnapshotStore,
    PostgresWorkflowBundleImportStore,
)
from studio_storage.bundle_workflow_import_port import WorkflowBundleImportConflict
from studio_storage.scheduler import WorkflowNotFound, WorkflowRunConflict
from studio_storage.scheduler_fencing import TaskAttemptId
from studio_storage.scheduler_leadership import SchedulerLeadershipLost

pytestmark = pytest.mark.skipif(
    not os.environ.get("RONIN_POSTGRES_TEST_DSN"),
    reason="real PostgreSQL qualification requires RONIN_POSTGRES_TEST_DSN",
)

NOW = Instant("2026-10-15T00:00:00.000000Z")


def _workflow(identifier: str, name: str | None = None) -> WorkflowDefinition:
    node = Node.create(operator=OperatorRef("notebook.run"), instance_key=f"task-{identifier}")
    return WorkflowDefinition(WorkflowId(identifier), name or identifier, Pipeline((node,)))


def test_postgres_workflow_and_schedule_bundle_import_is_atomic_and_idempotent() -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    store = PostgresWorkflowBundleImportStore(dsn, application_name="ronin-workflow-qualification")
    store.migrate()
    workspace_id = WorkspaceId(f"workflow-ws-{uuid4().hex}")
    store.create_workspace(Workspace(workspace_id, "Workflow qualification"), now=NOW)

    workflow = _workflow(f"workflow-{uuid4().hex}")
    schedule = Schedule(ScheduleId(f"schedule-{uuid4().hex}"), workflow.id, "0 * * * *")
    assert store.put_workflow(workspace_id, workflow, now=NOW) == workflow
    assert store.get_workflow(workspace_id, workflow.id) == workflow
    assert store.list_workflows(workspace_id) == (workflow,)
    assert store.get_workflow(workspace_id, WorkflowId("missing")) is None
    assert store.get_schedule(workspace_id, schedule.id) is None
    assert store.list_schedules(workspace_id) == ()

    first = store.commit_workflow_import(workspace_id, (workflow,), (schedule,), now=NOW)
    second = store.commit_workflow_import(workspace_id, (workflow,), (schedule,), now=NOW)
    assert (first.workflows_created, first.schedules_created) == (0, 1)
    assert (second.workflows_created, second.schedules_created) == (0, 0)
    assert store.get_schedule(workspace_id, schedule.id) == schedule
    assert store.list_schedules(workspace_id) == (schedule,)

    with pytest.raises(WorkflowBundleImportConflict, match="different portable definition"):
        store.commit_workflow_import(
            workspace_id, (_workflow(workflow.id.value, "conflict"),), (), now=NOW
        )
    with pytest.raises(WorkflowBundleImportConflict, match="different portable definition"):
        store.commit_workflow_import(
            workspace_id, (workflow,), (Schedule(schedule.id, workflow.id, "5 * * * *"),), now=NOW
        )
    with pytest.raises(ValueError, match="unique ids"):
        store.commit_workflow_import(workspace_id, (workflow,), (schedule, schedule), now=NOW)
    with pytest.raises(ValueError, match="must reference"):
        store.commit_workflow_import(
            workspace_id,
            (workflow,),
            (Schedule(ScheduleId("orphan"), WorkflowId("missing"), "0 * * * *"),),
            now=NOW,
        )


def test_postgres_workflow_mutations_require_active_workspace() -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    store = PostgresWorkflowBundleImportStore(dsn, application_name="ronin-workflow-qualification")
    store.migrate()
    workspace_id = WorkspaceId(f"archived-workflow-{uuid4().hex}")
    metadata = PostgresMetadataStore(dsn, application_name="ronin-workflow-qualification")
    workspace = Workspace(workspace_id, "Archived workflow qualification")
    metadata.create_workspace(workspace, now=NOW)
    metadata.update_workspace(Workspace(workspace_id, workspace.name, state="archived"), now=NOW)
    with pytest.raises(WorkflowBundleImportConflict, match="archived"):
        store.put_workflow(workspace_id, _workflow("blocked"), now=NOW)
    with pytest.raises(WorkflowBundleImportConflict, match="does not exist"):
        store.put_workflow(WorkspaceId("missing-workspace"), _workflow("missing"), now=NOW)


def test_postgres_scheduler_run_and_task_snapshots_are_atomic_and_idempotent() -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    store = PostgresSchedulerSnapshotStore(
        dsn,
        application_name="ronin-scheduler-snapshot-qualification",
    )
    workspace_id = WorkspaceId(f"scheduler-snapshot-ws-{uuid4().hex}")
    store.create_workspace(Workspace(workspace_id, "Scheduler snapshot qualification"), now=NOW)
    workflow = _workflow(f"scheduler-snapshot-workflow-{uuid4().hex}")
    store.put_workflow(workspace_id, workflow, now=NOW)
    run_id = WorkflowRunId(f"scheduler-snapshot-run-{uuid4().hex}")
    trigger = Trigger("manual", f"trigger-{uuid4().hex}")

    run = store.create_run(workspace_id, run_id, workflow.id, trigger, now=NOW)
    assert store.get_run(workspace_id, run_id) == run
    tasks = store.list_task_runs(workspace_id, run_id)
    assert len(tasks) == len(workflow.pipeline.nodes)
    assert {task.node_id for task in tasks} == {node.id for node in workflow.pipeline.nodes}
    assert all(task.state == "pending" and task.attempt_count == 0 for task in tasks)
    assert store.get_run(WorkspaceId(f"other-{workspace_id}"), run_id) is None
    assert store.list_task_runs(WorkspaceId(f"other-{workspace_id}"), run_id) == ()

    branch_node = tasks[0].node_id
    expression = {"op": "equals", "field": "environment", "value": "prod"}
    context = {"environment": "dev"}
    decision = store.apply_branch_decision(
        workspace_id,
        run_id,
        branch_node,
        expression,
        context,
        now=NOW,
    )
    assert not decision.should_run
    assert store.get_branch_decision(workspace_id, run_id, branch_node) == decision
    assert (
        store.apply_branch_decision(
            workspace_id,
            run_id,
            branch_node,
            expression,
            context,
            now=NOW,
        )
        == decision
    )
    assert (
        next(
            item
            for item in store.list_task_runs(workspace_id, run_id)
            if item.node_id == branch_node
        ).state
        == "blocked"
    )
    with pytest.raises(WorkflowRunConflict, match="different content"):
        store.apply_branch_decision(
            workspace_id,
            run_id,
            branch_node,
            expression,
            {"environment": "prod"},
            now=NOW,
        )
    with pytest.raises(WorkflowNotFound, match="does not exist"):
        store.apply_branch_decision(
            workspace_id,
            run_id,
            NodeId("missing-node"),
            expression,
            context,
            now=NOW,
        )

    updated_workflow = WorkflowDefinition(workflow.id, "Updated workflow", workflow.pipeline)
    store.put_workflow(workspace_id, updated_workflow, now=NOW)
    assert store.get_workflow(workspace_id, workflow.id) == updated_workflow
    assert store.get_run(workspace_id, run_id) == run

    # Trigger identity is idempotent even when replay supplies a different run id.
    assert (
        store.create_run(
            workspace_id,
            WorkflowRunId(f"ignored-run-{uuid4().hex}"),
            workflow.id,
            trigger,
            now=NOW,
        )
        == run
    )
    with pytest.raises(WorkflowRunConflict, match="different trigger content"):
        store.create_run(
            workspace_id,
            WorkflowRunId(f"other-run-{uuid4().hex}"),
            workflow.id,
            Trigger("api", trigger.key),
            now=NOW,
        )
    with pytest.raises(WorkflowRunConflict, match="run id already exists"):
        store.create_run(
            workspace_id,
            run_id,
            workflow.id,
            Trigger("api", f"other-trigger-{uuid4().hex}"),
            now=NOW,
        )
    with pytest.raises(WorkflowNotFound):
        store.create_run(
            workspace_id,
            WorkflowRunId(f"missing-run-{uuid4().hex}"),
            WorkflowId("missing-workflow"),
            Trigger("manual", "missing-trigger"),
            now=NOW,
        )

    concurrent_trigger = Trigger("api", f"concurrent-trigger-{uuid4().hex}")
    candidate_run_ids = tuple(WorkflowRunId(f"concurrent-run-{uuid4().hex}") for _ in range(4))
    with ThreadPoolExecutor(max_workers=len(candidate_run_ids)) as executor:
        concurrent_runs = tuple(
            executor.map(
                lambda candidate: store.create_run(
                    workspace_id,
                    candidate,
                    workflow.id,
                    concurrent_trigger,
                    now=NOW,
                ),
                candidate_run_ids,
            )
        )
    assert len({item.id for item in concurrent_runs}) == 1
    assert len(store.list_task_runs(workspace_id, concurrent_runs[0].id)) == len(
        workflow.pipeline.nodes
    )

    reopened = PostgresSchedulerSnapshotStore(
        dsn,
        application_name="ronin-scheduler-snapshot-reopen-qualification",
    )
    assert reopened.get_run(workspace_id, run_id) == run
    reopened_tasks = reopened.list_task_runs(workspace_id, run_id)
    assert len(reopened_tasks) == len(tasks)
    assert next(item for item in reopened_tasks if item.node_id == branch_node).state == "blocked"
    assert reopened.get_branch_decision(workspace_id, run_id, branch_node) == decision


def test_postgres_scheduler_rejects_late_branch_decision_without_mutating_terminal_task() -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    store = PostgresSchedulerSnapshotStore(dsn)
    workspace_id = WorkspaceId(f"scheduler-late-branch-ws-{uuid4().hex}")
    store.create_workspace(Workspace(workspace_id, "Late branch"), now=NOW)
    workflow = _workflow(f"scheduler-late-branch-workflow-{uuid4().hex}")
    store.put_workflow(workspace_id, workflow, now=NOW)
    run_id = WorkflowRunId(f"scheduler-late-branch-run-{uuid4().hex}")
    store.create_run(workspace_id, run_id, workflow.id, Trigger("manual", "late"), now=NOW)
    node = workflow.pipeline.nodes[0]

    connection = store._connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE ronin_task_runs SET state='succeeded' "
                "WHERE workspace_id=%s AND workflow_run_id=%s",
                (str(workspace_id), str(run_id)),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    with pytest.raises(WorkflowRunConflict, match="after task execution has started"):
        store.apply_branch_decision(
            workspace_id,
            run_id,
            node.id,
            {"op": "equals", "field": "environment", "value": "prod"},
            {"environment": "dev"},
            now=NOW,
        )
    assert store.list_task_runs(workspace_id, run_id)[0].state == "succeeded"
    assert store.get_branch_decision(workspace_id, run_id, node.id) is None


def test_postgres_scheduler_attempt_leases_fence_workers_and_reclaim_expiry() -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    store = PostgresSchedulerSnapshotStore(dsn, application_name="ronin-scheduler-attempt-lease")
    workspace_id = WorkspaceId(f"scheduler-lease-ws-{uuid4().hex}")
    store.create_workspace(Workspace(workspace_id, "Scheduler lease"), now=NOW)
    node = Node.create(operator=OperatorRef("notebook.run"), instance_key="lease-task")
    workflow = WorkflowDefinition(
        WorkflowId(f"scheduler-lease-workflow-{uuid4().hex}"),
        "Scheduler lease",
        Pipeline((node,)),
        (
            TaskPolicy(
                node.id,
                retry=RetryPolicy(max_attempts=2),
                pool="lease-workers",
            ),
        ),
    )
    store.put_workflow(workspace_id, workflow, now=NOW)
    run_id = WorkflowRunId(f"scheduler-lease-run-{uuid4().hex}")
    store.create_run(workspace_id, run_id, workflow.id, Trigger("manual", "lease"), now=NOW)

    assert (
        store.claim_next_task(
            owner="worker-one",
            lease_token=LeaseToken(f"lease-{uuid4().hex}"),
            attempt_id=TaskAttemptId(f"attempt-{uuid4().hex}"),
            lease_seconds=30,
            now=NOW,
            workspace_id=workspace_id,
        )
        is None
    )
    pool = ResourcePoolDefinition("lease-workers", 1)
    assert store.put_resource_pool(workspace_id, pool, now=NOW) == pool
    assert store.put_resource_pool(workspace_id, pool, now=NOW) == pool
    assert store.get_resource_pool(workspace_id, pool.name) == pool
    assert store.list_resource_pools(workspace_id) == (pool,)

    first = store.claim_next_task(
        owner="worker-one",
        lease_token=LeaseToken(f"lease-{uuid4().hex}"),
        attempt_id=TaskAttemptId(f"attempt-{uuid4().hex}"),
        lease_seconds=30,
        now=NOW,
        workspace_id=workspace_id,
    )
    assert first is not None
    assert first.pool_name == pool.name
    assert store.resource_pool_usage(workspace_id, pool.name) == 1
    assert (
        store.claim_next_task(
            owner="worker-two",
            lease_token=LeaseToken(f"lease-{uuid4().hex}"),
            attempt_id=TaskAttemptId(f"attempt-{uuid4().hex}"),
            lease_seconds=30,
            now=NOW,
            workspace_id=workspace_id,
        )
        is None
    )

    with pytest.raises(ValueError, match="ownership lost"):
        store.heartbeat_task(
            workspace_id,
            first.attempt_id,
            owner="worker-two",
            lease_token=first.lease_token,
            lease_seconds=30,
            now=NOW,
        )

    expired_at = Instant("2026-10-15T00:00:31.000000Z")
    assert store.reclaim_expired(now=expired_at) == 1
    second = store.claim_next_task(
        owner="worker-two",
        lease_token=LeaseToken(f"lease-{uuid4().hex}"),
        attempt_id=TaskAttemptId(f"attempt-{uuid4().hex}"),
        lease_seconds=30,
        now=expired_at,
        workspace_id=workspace_id,
    )
    assert second is not None
    assert second.attempt_ordinal == 2
    with pytest.raises(ValueError, match="ownership lost"):
        store.complete_task(
            workspace_id,
            first.attempt_id,
            owner=first.lease_owner,
            lease_token=first.lease_token,
            succeeded=True,
            failure_code=None,
            now=expired_at,
        )

    renewed_until = store.heartbeat_task(
        workspace_id,
        second.attempt_id,
        owner=second.lease_owner,
        lease_token=second.lease_token,
        lease_seconds=60,
        now=expired_at,
    )
    assert renewed_until == Instant("2026-10-15T00:01:31.000000Z")
    store.complete_task(
        workspace_id,
        second.attempt_id,
        owner=second.lease_owner,
        lease_token=second.lease_token,
        succeeded=True,
        failure_code=None,
        now=expired_at,
    )
    assert store.get_run(workspace_id, run_id).state == "succeeded"  # type: ignore[union-attr]
    assert store.resource_pool_usage(workspace_id, pool.name) == 0


def test_postgres_scheduler_leadership_is_generation_fenced_and_persistent() -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    store = PostgresSchedulerLeadershipStore(dsn)
    # Docker qualification runs this suite more than once against one database.
    connection = store._connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM ronin_scheduler_leader_lease WHERE scope='scheduler'")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    assert store.get_scheduler_leader() is None
    first_token = LeaseToken(f"leader-token-{uuid4().hex}")
    first = store.acquire_scheduler_leadership(
        owner="leader-one",
        lease_token=first_token,
        lease_seconds=10,
        now=NOW,
    )
    assert first is not None
    assert first.generation == 1
    assert store.get_scheduler_leader() == first
    assert (
        store.acquire_scheduler_leadership(
            owner="leader-one",
            lease_token=first_token,
            lease_seconds=10,
            now=NOW,
        )
        == first
    )
    assert (
        store.acquire_scheduler_leadership(
            owner="leader-two",
            lease_token=LeaseToken(f"leader-token-{uuid4().hex}"),
            lease_seconds=10,
            now=NOW,
        )
        is None
    )
    assert (
        store.assert_scheduler_leadership(first, now=Instant("2026-10-15T00:00:05.000000Z"))
        == first
    )
    renewed = store.heartbeat_scheduler_leadership(
        first,
        lease_seconds=10,
        now=Instant("2026-10-15T00:00:05.000000Z"),
    )
    assert renewed.generation == first.generation
    assert renewed.lease_expires_at == Instant("2026-10-15T00:00:15.000000Z")

    replacement = store.acquire_scheduler_leadership(
        owner="leader-two",
        lease_token=LeaseToken(f"leader-token-{uuid4().hex}"),
        lease_seconds=10,
        now=Instant("2026-10-15T00:00:15.000000Z"),
    )
    assert replacement is not None
    assert replacement.generation == 2
    with pytest.raises(SchedulerLeadershipLost, match="lost"):
        store.assert_scheduler_leadership(renewed, now=Instant("2026-10-15T00:00:16.000000Z"))
    with pytest.raises(SchedulerLeadershipLost, match="lost"):
        store.heartbeat_scheduler_leadership(
            renewed,
            lease_seconds=10,
            now=Instant("2026-10-15T00:00:16.000000Z"),
        )
    with pytest.raises(SchedulerLeadershipLost, match="lost"):
        store.release_scheduler_leadership(renewed, now=Instant("2026-10-15T00:00:16.000000Z"))

    reopened = PostgresSchedulerLeadershipStore(dsn)
    assert reopened.get_scheduler_leader() == replacement
    reopened.release_scheduler_leadership(
        replacement,
        now=Instant("2026-10-15T00:00:16.000000Z"),
    )
    with pytest.raises(SchedulerLeadershipLost, match="lost"):
        reopened.assert_scheduler_leadership(
            replacement,
            now=Instant("2026-10-15T00:00:16.000000Z"),
        )
    contenders = (
        ("concurrent-one", LeaseToken(f"leader-token-{uuid4().hex}")),
        ("concurrent-two", LeaseToken(f"leader-token-{uuid4().hex}")),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        acquired = tuple(
            executor.map(
                lambda contender: reopened.acquire_scheduler_leadership(
                    owner=contender[0],
                    lease_token=contender[1],
                    lease_seconds=10,
                    now=Instant("2026-10-15T00:00:16.000000Z"),
                ),
                contenders,
            )
        )
    winners = tuple(item for item in acquired if item is not None)
    assert len(winners) == 1
    assert winners[0].generation == replacement.generation + 1
