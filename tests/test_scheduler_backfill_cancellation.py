from __future__ import annotations

import asyncio
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
from studio_execution import DurableExecutionService
from studio_execution.scheduler_backfill import SchedulerBackfillService
from studio_execution.scheduler_backfill_cancellation import cancel_backfill_group
from studio_orchestrator import Instant
from studio_storage import InMemoryJobStore
from studio_storage.scheduler_backfill import BackfillId, BackfillRequest
from studio_storage.scheduler_backfill_runtime import SchedulerBackfillRuntimeStore
from studio_storage.workspaces import SqliteWorkspaceStore

_T0 = Instant("2026-09-13T09:00:00.000000Z")
_T1 = Instant("2026-09-13T09:01:00.000000Z")
_WS = WorkspaceId("workspace-1")
_BACKFILL = BackfillId("backfill-1")


def _store(tmp_path: Path) -> SchedulerBackfillRuntimeStore:
    path = tmp_path / "ronin.sqlite3"
    workspaces = SqliteWorkspaceStore(path, migration_now=_T0)
    workspaces.create_workspace(Workspace(_WS, "Workspace"), now=_T0)
    store = SchedulerBackfillRuntimeStore(path, migration_now=_T0)
    node = Node.create(
        operator=OperatorRef("notebook.run"),
        instance_key="task",
        params={"target": "notebooks/demo.ronin.json", "parameters": {}},
    )
    workflow = WorkflowDefinition(WorkflowId("workflow-1"), "Workflow", Pipeline((node,)))
    schedule = Schedule(ScheduleId("schedule-1"), workflow.id, "* * * * *")
    store.put_workflow(_WS, workflow, now=_T0)
    store.put_schedule(_WS, schedule, now=_T0)
    store.create_backfill_plan(
        _WS,
        BackfillRequest(_BACKFILL, schedule.id, _T0, _T1),
        max_concurrency=1,
        now=_T0,
    )
    return store


def test_backfill_group_cancellation_terminalizes_created_workflows_and_is_idempotent(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    created = asyncio.run(SchedulerBackfillService(store).tick(_WS, _BACKFILL, now=_T0))
    assert len(created.fires) == 1
    workflow_run_id = created.fires[0].workflow_run_id
    workflow = store.get_run(_WS, workflow_run_id)
    assert workflow is not None
    assert workflow.state == "pending"

    async def scenario() -> None:
        service = DurableExecutionService(InMemoryJobStore())
        try:
            first = await cancel_backfill_group(
                store,
                service,
                _WS,
                _BACKFILL,
                now=_T1,
            )
            assert first.workflow_runs_seen == 1
            assert first.jobs_cancelled == 0

            second = await cancel_backfill_group(
                store,
                service,
                _WS,
                _BACKFILL,
                now=_T1,
            )
            assert second == first
        finally:
            await service.aclose()

    asyncio.run(scenario())

    request = store.get_backfill(_WS, _BACKFILL)
    assert request is not None
    assert request.state == "cancelled"
    workflow = store.get_run(_WS, workflow_run_id)
    assert workflow is not None
    assert workflow.state == "cancelled"
    tasks = store.list_task_runs(_WS, workflow_run_id)
    assert tasks
    assert all(task.state == "cancelled" for task in tasks)

    after = asyncio.run(SchedulerBackfillService(store).tick(_WS, _BACKFILL, now=_T1))
    assert after.fires == ()
