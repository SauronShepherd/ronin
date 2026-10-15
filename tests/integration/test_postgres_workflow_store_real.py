from __future__ import annotations

import os
from uuid import uuid4

import pytest
from studio_core import (
    Node,
    OperatorRef,
    Pipeline,
    Schedule,
    ScheduleId,
    WorkflowDefinition,
    WorkflowId,
    Workspace,
    WorkspaceId,
)
from studio_orchestrator import Instant
from studio_storage import PostgresMetadataStore, PostgresWorkflowBundleImportStore
from studio_storage.bundle_workflow_import_port import WorkflowBundleImportConflict

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
