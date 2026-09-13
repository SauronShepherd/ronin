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
from studio_execution.scheduler_backfill import SchedulerBackfillService
from studio_orchestrator import Instant, LeaseToken
from studio_storage.scheduler_backfill import BackfillId, BackfillRequest
from studio_storage.scheduler_backfill_runtime import SchedulerBackfillRuntimeStore
from studio_storage.scheduler_fencing import TaskAttemptId
from studio_storage.workspaces import SqliteWorkspaceStore

_T0 = Instant("2026-09-13T00:00:00.000000Z")
_T1 = Instant("2026-09-13T00:01:00.000000Z")
_T2 = Instant("2026-09-13T00:02:00.000000Z")
_WS = WorkspaceId("workspace-1")


def _workflow(name: str = "Original") -> WorkflowDefinition:
    node = Node.create(
        operator=OperatorRef("notebook.run"),
        instance_key="task",
        params={"target": "notebooks/demo.ronin.json", "parameters": {}},
    )
    return WorkflowDefinition(WorkflowId("workflow-1"), name, Pipeline((node,)))


def _store(tmp_path: Path) -> SchedulerBackfillRuntimeStore:
    path = tmp_path / "ronin.sqlite3"
    workspaces = SqliteWorkspaceStore(path, migration_now=_T0)
    workspaces.create_workspace(Workspace(_WS, "Workspace"), now=_T0)
    store = SchedulerBackfillRuntimeStore(path, migration_now=_T0)
    store.put_workflow(_WS, _workflow(), now=_T0)
    store.put_schedule(
        _WS,
        Schedule(ScheduleId("schedule-1"), WorkflowId("workflow-1"), "* * * * *"),
        now=_T0,
    )
    store.create_backfill_plan(
        _WS,
        BackfillRequest(BackfillId("backfill-1"), ScheduleId("schedule-1"), _T0, _T2),
        max_concurrency=1,
        now=_T0,
    )
    return store


def _complete_one(store: SchedulerBackfillRuntimeStore, ordinal: int, now: Instant) -> None:
    claim = store.claim_next_task(
        owner=f"worker-{ordinal}",
        lease_token=LeaseToken(f"lease-{ordinal}"),
        attempt_id=TaskAttemptId(f"attempt-{ordinal}"),
        lease_seconds=60,
        now=now,
        workspace_id=_WS,
    )
    assert claim is not None
    store.complete_task(
        _WS,
        claim.attempt_id,
        owner=claim.lease_owner,
        lease_token=claim.lease_token,
        succeeded=True,
        failure_code=None,
        now=now,
    )


def test_backfill_generation_respects_active_run_cap_and_independent_cursor(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    service = SchedulerBackfillService(store)

    first = asyncio.run(service.tick(_WS, BackfillId("backfill-1"), now=_T0))
    assert [run.logical_time for run in first.fires] == [_T0]
    assert first.active_runs == 1
    assert not first.generation_complete
    plan = store.get_backfill_plan(_WS, BackfillId("backfill-1"))
    assert plan is not None
    assert plan.cursor_at == _T0
    assert store.get_schedule_cursor(_WS, ScheduleId("schedule-1")) is None

    blocked = asyncio.run(service.tick(_WS, BackfillId("backfill-1"), now=_T0))
    assert blocked.fires == ()
    assert blocked.active_runs == 1
    assert store.get_backfill_plan(_WS, BackfillId("backfill-1")).cursor_at == _T0  # type: ignore[union-attr]

    _complete_one(store, 1, _T0)
    second = asyncio.run(service.tick(_WS, BackfillId("backfill-1"), now=_T1))
    assert [run.logical_time for run in second.fires] == [_T1]
    assert store.get_backfill_plan(_WS, BackfillId("backfill-1")).cursor_at == _T1  # type: ignore[union-attr]

    _complete_one(store, 2, _T1)
    third = asyncio.run(service.tick(_WS, BackfillId("backfill-1"), now=_T2))
    assert [run.logical_time for run in third.fires] == [_T2]
    assert third.generation_complete

    _complete_one(store, 3, _T2)
    final = asyncio.run(service.tick(_WS, BackfillId("backfill-1"), now=_T2))
    assert final.fires == ()
    assert final.active_runs == 0
    assert final.generation_complete
    request = store.get_backfill(_WS, BackfillId("backfill-1"))
    assert request is not None
    assert request.state == "completed"
    assert store.get_schedule_cursor(_WS, ScheduleId("schedule-1")) is None


def test_backfill_runs_use_workflow_snapshot_from_plan_creation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.put_workflow(_WS, _workflow("Changed live definition"), now=_T1)

    result = asyncio.run(
        SchedulerBackfillService(store).tick(_WS, BackfillId("backfill-1"), now=_T1)
    )
    assert len(result.fires) == 1
    run = store.get_run(_WS, result.fires[0].workflow_run_id)
    assert run is not None
    assert run.workflow_snapshot.name == "Original"
