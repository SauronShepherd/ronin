from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
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
from studio_core.scheduler_events import (
    EventTriggerDefinition,
    EventTriggerId,
    SchedulerEventId,
)
from studio_execution.scheduler_backfill import BackfillTickResult, SchedulerBackfillService
from studio_execution.scheduler_bridge import plan_scheduler_execution
from studio_orchestrator import Instant, JobState, LeaseToken
from studio_storage import (
    PostgresMetadataStore,
    PostgresSchedulerLeadershipStore,
    PostgresSchedulerSnapshotStore,
    PostgresWorkflowBundleImportStore,
)
from studio_storage.bundle_workflow_import_port import WorkflowBundleImportConflict
from studio_storage.scheduler import WorkflowNotFound, WorkflowRunConflict
from studio_storage.scheduler_backfill import (
    BackfillConflict,
    BackfillId,
    BackfillRequest,
    BackfillRun,
)
from studio_storage.scheduler_backfill_runtime import BackfillCapacityExhausted
from studio_storage.scheduler_events import (
    EventDelivery,
    SchedulerEventConflict,
    SchedulerEventRecord,
)
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


def test_postgres_scheduler_execution_outbox_survives_expiry_and_reconciles(
    request: pytest.FixtureRequest,
) -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    from studio_storage.postgres_core import _psycopg

    psycopg, _ = _psycopg()
    schema = f"scheduler_outbox_{uuid4().hex}"
    connection = psycopg.connect(dsn)
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE SCHEMA {schema}")
        connection.commit()
    finally:
        connection.close()
    schema_dsn = psycopg.conninfo.make_conninfo(dsn, options=f"-c search_path={schema},public")

    def drop_schema() -> None:
        cleanup = psycopg.connect(dsn)
        try:
            with cleanup.cursor() as cursor:
                cursor.execute(f"DROP SCHEMA {schema} CASCADE")
            cleanup.commit()
        finally:
            cleanup.close()

    request.addfinalizer(drop_schema)
    store = PostgresSchedulerSnapshotStore(schema_dsn, application_name="ronin-scheduler-outbox")
    connection = store._connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE ronin_scheduler_backfill_runs")
            cursor.execute("DROP TABLE ronin_scheduler_backfill_plans")
            cursor.execute("DROP TABLE ronin_scheduler_backfills")
            cursor.execute("DROP TABLE ronin_scheduler_event_deliveries")
            cursor.execute("DROP TABLE ronin_scheduler_events")
            cursor.execute("DROP TABLE ronin_event_triggers")
            cursor.execute("DROP TABLE ronin_task_execution_intents")
            cursor.execute("DROP TABLE ronin_task_execution_links")
            cursor.execute("DELETE FROM ronin_scheduler_schema_migrations WHERE version>=4")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    # Exercise the production upgrade path from the current schema-3 main branch.
    store = PostgresSchedulerSnapshotStore(schema_dsn, application_name="ronin-scheduler-outbox")
    workspace_id = WorkspaceId(f"scheduler-outbox-ws-{uuid4().hex}")
    store.create_workspace(Workspace(workspace_id, "Scheduler outbox"), now=NOW)
    workflow_id = WorkflowId(f"scheduler-outbox-workflow-{uuid4().hex}")
    node = Node.create(
        operator=OperatorRef("notebook.run"),
        instance_key=f"task-{uuid4().hex}",
        params={"target": "notebooks/demo.ronin.json", "parameters": {}},
    )
    workflow = WorkflowDefinition(workflow_id, "Scheduler outbox", Pipeline((node,)))
    store.put_workflow(workspace_id, workflow, now=NOW)
    run = store.create_run(
        workspace_id,
        WorkflowRunId(f"scheduler-outbox-run-{uuid4().hex}"),
        workflow.id,
        Trigger("manual", f"outbox-{uuid4().hex}"),
        now=NOW,
    )
    claim = store.claim_next_task(
        owner="outbox-worker",
        lease_token=LeaseToken(f"lease-{uuid4().hex}"),
        attempt_id=TaskAttemptId(f"attempt-{uuid4().hex}"),
        lease_seconds=30,
        now=NOW,
        workspace_id=workspace_id,
    )
    assert claim is not None
    plan = plan_scheduler_execution(claim, run, "postgres-outbox-project", now=NOW)
    intent = store.put_execution_intent(
        workspace_id,
        claim.attempt_id,
        job=plan.job,
        run=plan.run,
        owner=claim.lease_owner,
        lease_token=claim.lease_token,
        now=NOW,
    )
    assert (
        store.put_execution_intent(
            workspace_id,
            claim.attempt_id,
            job=plan.job,
            run=plan.run,
            owner=claim.lease_owner,
            lease_token=claim.lease_token,
            now=NOW,
        )
        == intent
    )
    assert store.get_execution_link(workspace_id, claim.attempt_id) == intent.link
    assert store.get_execution_intent(workspace_id, claim.attempt_id) == intent
    assert intent in store.list_execution_intents()

    expired_at = Instant("2026-10-15T00:00:31.000000Z")
    store.reclaim_expired(now=expired_at)
    connection = store._connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT state FROM ronin_task_attempts "
                "WHERE workspace_id=%s AND task_attempt_id=%s",
                (str(workspace_id), str(claim.attempt_id)),
            )
            attempt_state = cursor.fetchone()["state"]
        connection.commit()
    finally:
        connection.close()
    assert attempt_state == "running"
    assert (
        store.claim_next_task(
            owner="outbox-worker-restarted",
            lease_token=LeaseToken(f"lease-{uuid4().hex}"),
            attempt_id=TaskAttemptId(f"attempt-{uuid4().hex}"),
            lease_seconds=30,
            now=expired_at,
            workspace_id=workspace_id,
        )
        is None
    )

    terminal = replace(
        plan.job,
        state=JobState.SUCCEEDED,
        updated_at=expired_at,
    )
    assert store.reconcile_execution(
        workspace_id,
        claim.attempt_id,
        terminal,
        now=expired_at,
    )
    assert store.get_run(workspace_id, run.id).state == "succeeded"  # type: ignore[union-attr]
    assert store.reconcile_execution(
        workspace_id,
        claim.attempt_id,
        terminal,
        now=expired_at,
    )


def test_postgres_scheduler_event_inbox_freezes_and_replays_deliveries(
    request: pytest.FixtureRequest,
) -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    from studio_storage.postgres_core import _psycopg

    psycopg, _ = _psycopg()
    schema = f"scheduler_events_{uuid4().hex}"
    connection = psycopg.connect(dsn)
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE SCHEMA {schema}")
        connection.commit()
    finally:
        connection.close()
    schema_dsn = psycopg.conninfo.make_conninfo(dsn, options=f"-c search_path={schema},public")

    def drop_schema() -> None:
        cleanup = psycopg.connect(dsn)
        try:
            with cleanup.cursor() as cursor:
                cursor.execute(f"DROP SCHEMA {schema} CASCADE")
            cleanup.commit()
        finally:
            cleanup.close()

    request.addfinalizer(drop_schema)
    store = PostgresSchedulerSnapshotStore(schema_dsn, application_name="ronin-scheduler-events")
    connection = store._connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE ronin_scheduler_backfill_runs")
            cursor.execute("DROP TABLE ronin_scheduler_backfill_plans")
            cursor.execute("DROP TABLE ronin_scheduler_backfills")
            cursor.execute("DROP TABLE ronin_scheduler_event_deliveries")
            cursor.execute("DROP TABLE ronin_scheduler_events")
            cursor.execute("DROP TABLE ronin_event_triggers")
            cursor.execute("DELETE FROM ronin_scheduler_schema_migrations WHERE version>=5")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    # Exercise the production upgrade path from the current schema-4 main branch.
    store = PostgresSchedulerSnapshotStore(schema_dsn, application_name="ronin-scheduler-events")

    workspace_id = WorkspaceId(f"scheduler-events-ws-{uuid4().hex}")
    store.create_workspace(Workspace(workspace_id, "Scheduler events"), now=NOW)
    workflow = _workflow(f"scheduler-events-workflow-{uuid4().hex}")
    store.put_workflow(workspace_id, workflow, now=NOW)
    definition = EventTriggerDefinition(
        EventTriggerId(f"trigger-{uuid4().hex}"),
        workflow.id,
        "asset.updated",
        source_ref="catalog",
        subject_ref="asset-1",
    )
    assert store.put_event_trigger(workspace_id, definition, now=NOW) == definition
    assert store.put_event_trigger(workspace_id, definition, now=NOW) == definition
    assert store.list_event_triggers(workspace_id) == (definition,)

    event = SchedulerEventRecord(
        workspace_id,
        SchedulerEventId(f"event-{uuid4().hex}"),
        "asset.updated",
        "catalog",
        "asset-1",
        "a" * 64,
        NOW,
        NOW,
    )
    deliveries = store.ingest_event(event)
    assert deliveries == (EventDelivery(workspace_id, event.id, definition),)
    assert store.get_event(workspace_id, event.id) == event
    with ThreadPoolExecutor(max_workers=2) as executor:
        replayed = tuple(executor.map(lambda _index: store.ingest_event(event), range(2)))
    assert replayed == (deliveries, deliveries)
    with pytest.raises(SchedulerEventConflict, match="conflicting content"):
        store.ingest_event(replace(event, payload_digest="b" * 64))

    updated = replace(definition, event_type="asset.deleted")
    store.put_event_trigger(workspace_id, updated, now=NOW)
    assert store.ingest_event(event) == deliveries
    assert store.list_pending_deliveries(workspace_id) == deliveries
    alternate_workflow = _workflow(f"scheduler-events-alternate-{uuid4().hex}")
    store.put_workflow(workspace_id, alternate_workflow, now=NOW)
    forged = replace(
        deliveries[0],
        trigger=replace(definition, workflow_id=alternate_workflow.id),
    )
    with pytest.raises(SchedulerEventConflict, match="frozen snapshot"):
        store.deliver_event(forged, now=NOW)
    assert store.list_pending_deliveries(workspace_id) == deliveries

    with ThreadPoolExecutor(max_workers=2) as executor:
        delivered_results = tuple(
            executor.map(
                lambda _index: store.deliver_event(deliveries[0], now=NOW),
                range(2),
            )
        )
    delivered = delivered_results[0]
    assert delivered.state == "delivered"
    assert delivered.workflow_run_id is not None
    assert delivered_results == (delivered, delivered)
    assert store.deliver_event(deliveries[0], now=NOW) == delivered
    assert store.list_pending_deliveries(workspace_id) == ()
    assert store.get_run(workspace_id, delivered.workflow_run_id) is not None

    unmatched = replace(
        event,
        id=SchedulerEventId(f"event-{uuid4().hex}"),
        event_type="asset.updated",
        subject_ref="asset-2",
    )
    assert store.ingest_event(unmatched) == ()


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


def test_postgres_scheduler_backfill_runs_through_the_service_and_survives_reopen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    store = PostgresSchedulerSnapshotStore(dsn, application_name="ronin-scheduler-backfill")
    workspace_id = WorkspaceId(f"scheduler-backfill-ws-{uuid4().hex}")
    store.create_workspace(Workspace(workspace_id, "Scheduler backfill"), now=NOW)
    workflow = _workflow(f"scheduler-backfill-workflow-{uuid4().hex}")
    schedule = Schedule(
        ScheduleId(f"scheduler-backfill-schedule-{uuid4().hex}"), workflow.id, "* * * * *"
    )
    store.commit_workflow_import(workspace_id, (workflow,), (schedule,), now=NOW)
    start = Instant("2026-10-15T00:01:00.000000Z")
    end = Instant("2026-10-15T00:02:00.000000Z")
    backfill = BackfillRequest(
        BackfillId(f"scheduler-backfill-{uuid4().hex}"), schedule.id, start, end
    )
    plan = store.create_backfill_plan(workspace_id, backfill, max_concurrency=1, now=NOW)
    assert store.create_backfill_plan(workspace_id, backfill, max_concurrency=1, now=NOW) == plan
    with pytest.raises(BackfillConflict, match="generation is not complete"):
        store.complete_backfill(workspace_id, backfill.id, now=NOW)
    with pytest.raises(BackfillConflict, match="different content"):
        store.create_backfill_plan(workspace_id, backfill, max_concurrency=2, now=NOW)
    with pytest.raises(ValueError, match="max_concurrency must be positive"):
        store.create_backfill_plan(workspace_id, backfill, max_concurrency=0, now=NOW)

    standalone = BackfillRequest(
        BackfillId(f"scheduler-backfill-standalone-{uuid4().hex}"), schedule.id, start, end
    )
    assert store.create_backfill(workspace_id, standalone, now=NOW) == standalone
    assert store.create_backfill(workspace_id, standalone, now=NOW) == standalone
    assert store.get_backfill(workspace_id, standalone.id) == standalone
    assert store.get_backfill(workspace_id, BackfillId("missing-backfill")) is None
    with pytest.raises(BackfillConflict, match="different content"):
        store.create_backfill(
            workspace_id,
            replace(standalone, end_at=Instant("2026-10-15T00:03:00.000000Z")),
            now=NOW,
        )
    with pytest.raises(ValueError, match="start pending"):
        store.create_backfill(workspace_id, replace(standalone, state="running"), now=NOW)
    with pytest.raises(BackfillConflict, match="schedule does not exist"):
        store.create_backfill(
            workspace_id,
            replace(
                standalone,
                id=BackfillId(f"missing-schedule-{uuid4().hex}"),
                schedule_id=ScheduleId("missing"),
            ),
            now=NOW,
        )

    # Workflow edits after plan creation must not alter the historical snapshot.
    updated_workflow = WorkflowDefinition(workflow.id, "Updated", workflow.pipeline)
    store.put_workflow(workspace_id, updated_workflow, now=NOW)
    service = SchedulerBackfillService(store)
    reservation = store._reserve_snapshot_backfill_run(workspace_id, backfill.id, start, now=NOW)
    assert reservation.state == "reserved"

    async def generate_first_fire() -> tuple[BackfillTickResult, BackfillTickResult]:
        return await asyncio.gather(
            service.tick(workspace_id, backfill.id, now=NOW, max_new_runs=1),
            service.tick(workspace_id, backfill.id, now=NOW, max_new_runs=1),
        )

    first_results = asyncio.run(generate_first_fire())
    assert all(result.active_runs == 1 for result in first_results)
    first_runs = store.list_backfill_runs(workspace_id, backfill.id)
    assert len(first_runs) == 1
    assert first_runs[0].state == "created"
    first_id = first_runs[0].workflow_run_id
    stored_first = store.get_run(workspace_id, first_id)
    assert stored_first is not None
    assert stored_first.workflow_snapshot.name == workflow.name
    assert store.count_active_backfill_runs(workspace_id, backfill.id) == 1
    assert len(store.list_task_runs(workspace_id, first_id)) == len(workflow.pipeline.nodes)

    # A new logical slot is throttled until the previous workflow is terminal.
    with pytest.raises(BackfillCapacityExhausted):
        store.create_snapshot_backfill_run(workspace_id, backfill.id, logical_time=end, now=NOW)
    connection = store._connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE ronin_workflow_runs SET state='succeeded' "
                "WHERE workspace_id=%s AND workflow_run_id=%s",
                (str(workspace_id), str(first_id)),
            )
        connection.commit()
    finally:
        connection.close()
    assert store.count_active_backfill_runs(workspace_id, backfill.id) == 0

    second_result = asyncio.run(service.tick(workspace_id, backfill.id, now=NOW))
    assert len(second_result.fires) == 1
    assert second_result.fires[0].logical_time == end
    assert second_result.generation_complete
    assert len(store.list_backfill_runs(workspace_id, backfill.id)) == 2
    with pytest.raises(BackfillConflict, match="still has active runs"):
        store.complete_backfill(workspace_id, backfill.id, now=NOW)
    with pytest.raises(BackfillConflict, match="cannot be reopened"):
        store.advance_backfill_cursor(
            workspace_id,
            backfill.id,
            through=end,
            generation_complete=False,
            now=NOW,
        )
    with pytest.raises(ValueError, match="must not move backwards"):
        store.advance_backfill_cursor(
            workspace_id,
            backfill.id,
            through=start,
            generation_complete=False,
            now=NOW,
        )

    second_id = second_result.fires[0].workflow_run_id
    connection = store._connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE ronin_workflow_runs SET state='succeeded' "
                "WHERE workspace_id=%s AND workflow_run_id=%s",
                (str(workspace_id), str(second_id)),
            )
        connection.commit()
    finally:
        connection.close()
    final_result = asyncio.run(service.tick(workspace_id, backfill.id, now=NOW))
    assert final_result.generation_complete
    assert store.get_backfill(workspace_id, backfill.id) == replace(backfill, state="completed")
    with pytest.raises(BackfillConflict, match="completed backfill cannot be cancelled"):
        store.cancel_backfill(workspace_id, backfill.id, now=NOW)

    cancelled = BackfillRequest(
        BackfillId(f"scheduler-backfill-cancelled-{uuid4().hex}"), schedule.id, start, end
    )
    store.create_backfill_plan(workspace_id, cancelled, max_concurrency=1, now=NOW)
    assert store.cancel_backfill(workspace_id, cancelled.id, now=NOW) == replace(
        cancelled, state="cancelled"
    )
    assert store.cancel_backfill(workspace_id, cancelled.id, now=NOW) == replace(
        cancelled, state="cancelled"
    )
    with pytest.raises(KeyError, match="missing-backfill"):
        store.cancel_backfill(workspace_id, BackfillId("missing-backfill"), now=NOW)
    with pytest.raises(BackfillConflict, match="cannot reserve run for cancelled backfill"):
        store.create_snapshot_backfill_run(workspace_id, cancelled.id, logical_time=start, now=NOW)
    with pytest.raises(BackfillConflict, match="cancelled backfill cannot be completed"):
        store.complete_backfill(workspace_id, cancelled.id, now=NOW)
    reopened = PostgresSchedulerSnapshotStore(dsn, application_name="ronin-scheduler-backfill")
    assert reopened.list_backfill_runs(workspace_id, backfill.id) == store.list_backfill_runs(
        workspace_id, backfill.id
    )

    racing_cancel = BackfillRequest(
        BackfillId(f"scheduler-backfill-racing-cancel-{uuid4().hex}"), schedule.id, start, end
    )
    store.create_backfill_plan(workspace_id, racing_cancel, max_concurrency=1, now=NOW)
    reserve = store._reserve_snapshot_backfill_run

    def reserve_then_cancel(
        target_workspace: WorkspaceId,
        target_backfill: BackfillId,
        logical_time: Instant,
        *,
        now: Instant,
    ) -> BackfillRun:
        reserved = reserve(target_workspace, target_backfill, logical_time, now=now)
        store.cancel_backfill(target_workspace, target_backfill, now=now)
        return reserved

    with monkeypatch.context() as patch:
        patch.setattr(store, "_reserve_snapshot_backfill_run", reserve_then_cancel)
        with pytest.raises(BackfillConflict, match="cancelled backfill cannot create"):
            store.create_snapshot_backfill_run(
                workspace_id, racing_cancel.id, logical_time=start, now=NOW
            )
    racing_runs = store.list_backfill_runs(workspace_id, racing_cancel.id)
    assert len(racing_runs) == 1
    assert racing_runs[0].state == "reserved"
    assert store.get_run(workspace_id, racing_runs[0].workflow_run_id) is None


def test_postgres_scheduler_backfill_migrates_schema_five_to_six(
    request: pytest.FixtureRequest,
) -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    from studio_storage.postgres_core import _psycopg

    psycopg, _ = _psycopg()
    schema = f"scheduler_backfill_migration_{uuid4().hex}"
    connection = psycopg.connect(dsn)
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE SCHEMA {schema}")
        connection.commit()
    finally:
        connection.close()
    schema_dsn = psycopg.conninfo.make_conninfo(dsn, options=f"-c search_path={schema},public")

    def drop_schema() -> None:
        cleanup = psycopg.connect(dsn)
        try:
            with cleanup.cursor() as cursor:
                cursor.execute(f"DROP SCHEMA {schema} CASCADE")
            cleanup.commit()
        finally:
            cleanup.close()

    request.addfinalizer(drop_schema)
    store = PostgresSchedulerSnapshotStore(schema_dsn, application_name="ronin-backfill-migration")
    connection = store._connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE ronin_scheduler_backfill_runs")
            cursor.execute("DROP TABLE ronin_scheduler_backfill_plans")
            cursor.execute("DROP TABLE ronin_scheduler_backfills")
            cursor.execute("DELETE FROM ronin_scheduler_schema_migrations WHERE version=6")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    PostgresSchedulerSnapshotStore(schema_dsn, application_name="ronin-backfill-migration")
    connection = psycopg.connect(schema_dsn)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version FROM ronin_scheduler_schema_migrations ORDER BY version")
            assert [int(row[0]) for row in cursor.fetchall()] == [1, 2, 3, 4, 5, 6]
            for table in (
                "ronin_scheduler_backfills",
                "ronin_scheduler_backfill_plans",
                "ronin_scheduler_backfill_runs",
            ):
                cursor.execute("SELECT to_regclass(%s) AS table_name", (table,))
                assert cursor.fetchone()[0] == table
    finally:
        connection.close()
