from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from studio_core import (
    Node,
    OperatorRef,
    Pipeline,
    Schedule,
    ScheduleId,
    Trigger,
    WorkflowDefinition,
    WorkflowId,
    WorkflowRunId,
    Workspace,
    WorkspaceId,
)
from studio_orchestrator import Instant
from studio_storage import (
    PostgresMetadataStore,
    PostgresSchedulerSnapshotStore,
    PostgresWorkflowBundleImportStore,
)
from studio_storage.bundle_workflow_import_port import WorkflowBundleImportConflict
from studio_storage.scheduler import WorkflowNotFound, WorkflowRunConflict

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
    assert reopened.list_task_runs(workspace_id, run_id) == tasks
