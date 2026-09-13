from __future__ import annotations

import asyncio
from pathlib import Path

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
from studio_execution.scheduler_leadership import SchedulerLeadershipGuard
from studio_execution.scheduler_schedule_service import SchedulerScheduleService
from studio_orchestrator import Instant, LeaseToken
from studio_storage.scheduler_leadership import SchedulerLeadershipLost, SchedulerLeadershipStore
from studio_storage.scheduler_schedule import SchedulerScheduleStore
from studio_storage.workspaces import SqliteWorkspaceStore

_T0 = Instant("2026-09-13T08:40:00.000000Z")
_T10 = Instant("2026-09-13T08:40:10.000000Z")
_WS = WorkspaceId("workspace-1")


def test_stale_leader_cannot_fire_cron_or_advance_cursor(tmp_path: Path) -> None:
    path = tmp_path / "ronin.sqlite3"
    workspaces = SqliteWorkspaceStore(path, migration_now=_T0)
    workspaces.create_workspace(Workspace(_WS, "Workspace"), now=_T0)

    schedule_store = SchedulerScheduleStore(path, migration_now=_T0)
    node = Node.create(operator=OperatorRef("notebook.run"), instance_key="task")
    workflow = WorkflowDefinition(WorkflowId("workflow-1"), "Workflow", Pipeline((node,)))
    schedule = Schedule(ScheduleId("every-minute"), workflow.id, "* * * * *")
    schedule_store.put_workflow(_WS, workflow, now=_T0)
    schedule_store.put_schedule(_WS, schedule, now=_T0)

    leadership_store = SchedulerLeadershipStore(path, migration_now=_T0)
    lease = leadership_store.acquire_scheduler_leadership(
        owner="scheduler-a",
        lease_token=LeaseToken("leader-a"),
        lease_seconds=30,
        now=_T0,
    )
    assert lease is not None
    guard = SchedulerLeadershipGuard(leadership_store, lease)
    leadership_store.release_scheduler_leadership(lease, now=_T10)

    service = SchedulerScheduleService(schedule_store, authority_check=guard.check)

    async def scenario() -> None:
        with pytest.raises(SchedulerLeadershipLost):
            await service.tick(
                _WS,
                through=Instant("2026-09-13T08:41:00.000000Z"),
                now=_T10,
            )

    asyncio.run(scenario())
    assert schedule_store.list_schedule_fires(_WS, schedule.id) == ()
    assert schedule_store.get_schedule_cursor(_WS, schedule.id) is None
