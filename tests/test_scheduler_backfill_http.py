from __future__ import annotations

from pathlib import Path

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
from studio_execution import SqliteWorkflowHTTPAdapter
from studio_orchestrator import Instant
from studio_storage.scheduler_backfill import BackfillId, BackfillRequest
from studio_storage.scheduler_backfill_runtime import SchedulerBackfillRuntimeStore
from studio_storage.workspaces import SqliteWorkspaceStore

_NOW = Instant("2026-10-30T10:00:00.000000Z")
_WORKSPACE = WorkspaceId("workspace-1")


def test_http_backfill_creation_persists_immutable_runtime_plan(tmp_path: Path) -> None:
    database = tmp_path / "ronin.sqlite3"
    workspaces = SqliteWorkspaceStore(database, migration_now=_NOW)
    workspaces.create_workspace(Workspace(_WORKSPACE, "Workspace"), now=_NOW)
    store = SchedulerBackfillRuntimeStore(database, migration_now=_NOW)
    workflow = WorkflowDefinition(
        WorkflowId("workflow-1"),
        "Workflow",
        Pipeline(
            (
                Node.create(
                    operator=OperatorRef("notebook.run"),
                    instance_key="task",
                    params={"target": "notebooks/demo.ronin.json", "parameters": {}},
                ),
            )
        ),
    )
    schedule = Schedule(ScheduleId("schedule-1"), workflow.id, "0 0 * * *")
    store.put_workflow(_WORKSPACE, workflow, now=_NOW)
    store.put_schedule(_WORKSPACE, schedule, now=_NOW)
    adapter = SqliteWorkflowHTTPAdapter(store, now=_NOW)
    request = BackfillRequest(
        BackfillId("backfill-1"),
        schedule.id,
        Instant("2026-10-29T00:00:00.000000Z"),
        Instant("2026-10-30T00:00:00.000000Z"),
    )

    assert adapter.create_backfill(_WORKSPACE, request) == request
    plan = store.get_backfill_plan(_WORKSPACE, request.id)
    assert plan is not None
    assert plan.schedule_snapshot == schedule
    assert plan.workflow_snapshot == workflow
    assert plan.max_concurrency == 4
    assert store.list_active_backfills(_WORKSPACE) == (request.id,)
