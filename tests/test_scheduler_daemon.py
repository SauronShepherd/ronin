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
from studio_execution.scheduler_daemon import SchedulerDaemon, SchedulerDaemonWork
from studio_orchestrator import Instant, LeaseToken
from studio_storage import InMemoryJobStore
from studio_storage.scheduler_backfill_runtime import SchedulerBackfillRuntimeStore
from studio_storage.scheduler_events import SchedulerEventStore
from studio_storage.scheduler_fencing import TaskAttemptId
from studio_storage.scheduler_leadership import SchedulerLeadershipStore
from studio_storage.scheduler_schedule import SchedulerScheduleStore
from studio_storage.workspaces import SqliteWorkspaceStore

_T0 = Instant("2026-09-13T08:50:00.000000Z")
_T10 = Instant("2026-09-13T08:50:10.000000Z")
_T31 = Instant("2026-09-13T08:50:31.000000Z")
_WS = WorkspaceId("workspace-1")


class MutableClock:
    def __init__(self, value: Instant) -> None:
        self.value = value

    def __call__(self) -> Instant:
        return self.value


def _stores(tmp_path: Path):
    path = tmp_path / "ronin.sqlite3"
    workspaces = SqliteWorkspaceStore(path, migration_now=_T0)
    workspaces.create_workspace(Workspace(_WS, "Workspace"), now=_T0)
    return (
        SchedulerLeadershipStore(path, migration_now=_T0),
        SchedulerScheduleStore(path, migration_now=_T0),
        SchedulerEventStore(path, migration_now=_T0),
        SchedulerBackfillRuntimeStore(path, migration_now=_T0),
    )


def _daemon(
    *,
    leadership_store: SchedulerLeadershipStore,
    schedule_store: SchedulerScheduleStore,
    event_store: SchedulerEventStore,
    backfill_store: SchedulerBackfillRuntimeStore,
    service: DurableExecutionService,
    owner: str,
    clock: MutableClock,
    token: str,
) -> SchedulerDaemon:
    return SchedulerDaemon(
        leadership_store=leadership_store,
        schedule_store=schedule_store,
        event_store=event_store,
        backfill_store=backfill_store,
        job_service=service,
        owner=owner,
        clock=clock,
        leader_token_factory=lambda: LeaseToken(token),
        task_attempt_factory=lambda: TaskAttemptId(f"attempt-{owner}"),
        task_lease_token_factory=lambda: LeaseToken(f"task-{owner}"),
        leader_lease_seconds=30,
        task_lease_seconds=30,
    )


def test_daemon_leadership_is_exclusive_and_takeover_increments_generation(
    tmp_path: Path,
) -> None:
    leadership, schedules, events, backfills = _stores(tmp_path)
    clock_a = MutableClock(_T0)
    clock_b = MutableClock(_T10)

    async def scenario() -> None:
        service = DurableExecutionService(InMemoryJobStore())
        try:
            first = _daemon(
                leadership_store=leadership,
                schedule_store=schedules,
                event_store=events,
                backfill_store=backfills,
                service=service,
                owner="scheduler-a",
                clock=clock_a,
                token="leader-a",
            )
            second = _daemon(
                leadership_store=leadership,
                schedule_store=schedules,
                event_store=events,
                backfill_store=backfills,
                service=service,
                owner="scheduler-b",
                clock=clock_b,
                token="leader-b",
            )

            first_cycle = await first.run_once(SchedulerDaemonWork())
            assert first_cycle.is_leader
            assert first_cycle.leader_generation == 1

            blocked = await second.run_once(SchedulerDaemonWork())
            assert not blocked.is_leader
            assert blocked.leader_generation is None

            clock_b.value = _T31
            takeover = await second.run_once(SchedulerDaemonWork())
            assert takeover.is_leader
            assert takeover.leader_generation == 2
        finally:
            await service.aclose()

    asyncio.run(scenario())


def test_daemon_schedule_work_runs_under_durable_leadership(tmp_path: Path) -> None:
    leadership, schedules, events, backfills = _stores(tmp_path)
    node = Node.create(operator=OperatorRef("notebook.run"), instance_key="task")
    workflow = WorkflowDefinition(WorkflowId("workflow-1"), "Workflow", Pipeline((node,)))
    schedule = Schedule(ScheduleId("every-minute"), workflow.id, "* * * * *")
    schedules.put_workflow(_WS, workflow, now=_T0)
    schedules.put_schedule(_WS, schedule, now=_T0)
    clock = MutableClock(_T0)

    async def scenario() -> None:
        service = DurableExecutionService(InMemoryJobStore())
        try:
            daemon = _daemon(
                leadership_store=leadership,
                schedule_store=schedules,
                event_store=events,
                backfill_store=backfills,
                service=service,
                owner="scheduler-a",
                clock=clock,
                token="leader-a",
            )
            cycle = await daemon.run_once(
                SchedulerDaemonWork(schedule_workspaces=(_WS,))
            )
            assert cycle.is_leader
            assert cycle.leader_generation == 1
            assert cycle.schedule_fires == 1
            assert len(schedules.list_schedule_fires(_WS, schedule.id)) == 1

            clock.value = _T10
            await daemon.release()
            assert daemon.lease is None
        finally:
            await service.aclose()

    asyncio.run(scenario())
