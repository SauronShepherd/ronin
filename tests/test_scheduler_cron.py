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
from studio_execution.scheduler_cron import (
    CronExpression,
    CronSyntaxError,
    evaluated_minutes,
    schedule_matches,
)
from studio_execution.scheduler_schedule_service import (
    ScheduleFireLimitExceeded,
    SchedulerScheduleService,
)
from studio_orchestrator import Instant
from studio_storage.scheduler_schedule import SchedulerScheduleStore
from studio_storage.workspaces import SqliteWorkspaceStore

NOW = "2026-09-12T20:00:00.000000Z"


def _workflow() -> WorkflowDefinition:
    node = Node.create(operator=OperatorRef("notebook.run"), instance_key="task")
    return WorkflowDefinition(WorkflowId("workflow-1"), "Workflow", Pipeline((node,)))


def _store(tmp_path: Path) -> tuple[SchedulerScheduleStore, WorkspaceId, WorkflowDefinition]:
    database = tmp_path / "ronin.db"
    workspace_id = WorkspaceId("workspace-1")
    workspace_store = SqliteWorkspaceStore(database, migration_now=NOW)
    workspace_store.create_workspace(Workspace(workspace_id, "Workspace"), now=NOW)
    store = SchedulerScheduleStore(database, migration_now=NOW)
    workflow = _workflow()
    store.put_workflow(workspace_id, workflow, now=NOW)
    return store, workspace_id, workflow


def test_cron_expression_supports_lists_ranges_steps_and_posix_day_or() -> None:
    expression = CronExpression.parse("*/15 9-17 * * 1-5")
    assert expression.minute.values == frozenset({0, 15, 30, 45})
    assert expression.hour.values == frozenset(range(9, 18))

    # When both day-of-month and day-of-week are restricted, POSIX cron uses OR.
    either = CronExpression.parse("0 0 13 * 1")
    monday_not_13 = __import__("datetime").datetime(2026, 7, 6, tzinfo=__import__("datetime").UTC)
    assert either.matches_local(monday_not_13)


def test_cron_rejects_invalid_shape_ranges_and_steps() -> None:
    for expression in ("* * * *", "60 * * * *", "* 9-2 * * *", "*/0 * * * *"):
        with pytest.raises(CronSyntaxError):
            CronExpression.parse(expression)


def test_schedule_matches_iana_timezone() -> None:
    schedule = Schedule(
        ScheduleId("daily"),
        WorkflowId("workflow-1"),
        "0 9 * * *",
        timezone="Europe/Madrid",
    )
    # 2026-09-12 is CEST (UTC+2), so 07:00Z is 09:00 local.
    assert schedule_matches(schedule, Instant("2026-09-12T07:00:00.000000Z"))
    assert not schedule_matches(schedule, Instant("2026-09-12T08:00:00.000000Z"))


def test_evaluated_minutes_catches_up_and_fails_closed_on_large_gap() -> None:
    cursor = Instant("2026-09-12T10:00:00.000000Z")
    minutes = evaluated_minutes(
        cursor=cursor,
        through=Instant("2026-09-12T10:03:45.000000Z"),
        max_scan_minutes=3,
    )
    assert minutes == (
        Instant("2026-09-12T10:01:00.000000Z"),
        Instant("2026-09-12T10:02:00.000000Z"),
        Instant("2026-09-12T10:03:00.000000Z"),
    )
    with pytest.raises(RuntimeError, match="exceeding limit"):
        evaluated_minutes(
            cursor=cursor,
            through=Instant("2026-09-12T10:04:00.000000Z"),
            max_scan_minutes=3,
        )


def test_schedule_service_fires_once_and_catches_up_missed_minutes(tmp_path: Path) -> None:
    store, workspace_id, workflow = _store(tmp_path)
    schedule = Schedule(ScheduleId("every-minute"), workflow.id, "* * * * *")
    store.put_schedule(workspace_id, schedule, now=NOW)
    service = SchedulerScheduleService(store)

    async def scenario() -> None:
        first = await service.tick(
            workspace_id,
            through=Instant("2026-09-12T10:00:30.000000Z"),
            now=NOW,
        )
        assert [str(fire.scheduled_for) for fire in first.fires] == [
            "2026-09-12T10:00:00.000000Z"
        ]
        duplicate = await service.tick(
            workspace_id,
            through=Instant("2026-09-12T10:00:59.000000Z"),
            now=NOW,
        )
        assert duplicate.fires == ()

        caught_up = await service.tick(
            workspace_id,
            through=Instant("2026-09-12T10:03:00.000000Z"),
            now=NOW,
        )
        assert [str(fire.scheduled_for) for fire in caught_up.fires] == [
            "2026-09-12T10:01:00.000000Z",
            "2026-09-12T10:02:00.000000Z",
            "2026-09-12T10:03:00.000000Z",
        ]
        assert len(store.list_schedule_fires(workspace_id, schedule.id)) == 4

    asyncio.run(scenario())


def test_disabled_schedule_advances_cursor_without_backfilling_disabled_minute(
    tmp_path: Path,
) -> None:
    store, workspace_id, workflow = _store(tmp_path)
    schedule = Schedule(ScheduleId("toggle"), workflow.id, "* * * * *", enabled=False)
    store.put_schedule(workspace_id, schedule, now=NOW)
    service = SchedulerScheduleService(store)

    async def scenario() -> None:
        disabled = await service.tick(
            workspace_id,
            through=Instant("2026-09-12T10:00:00.000000Z"),
            now=NOW,
        )
        assert disabled.fires == ()
        store.put_schedule(
            workspace_id,
            Schedule(schedule.id, workflow.id, schedule.cron, enabled=True),
            now=NOW,
        )
        enabled = await service.tick(
            workspace_id,
            through=Instant("2026-09-12T10:01:00.000000Z"),
            now=NOW,
        )
        assert [str(fire.scheduled_for) for fire in enabled.fires] == [
            "2026-09-12T10:01:00.000000Z"
        ]

    asyncio.run(scenario())


def test_tick_fire_limit_fails_before_creating_runs(tmp_path: Path) -> None:
    store, workspace_id, workflow = _store(tmp_path)
    schedule = Schedule(ScheduleId("limited"), workflow.id, "* * * * *")
    store.put_schedule(workspace_id, schedule, now=NOW)
    store.advance_schedule_cursor(
        workspace_id,
        schedule.id,
        through=Instant("2026-09-12T10:00:00.000000Z"),
        now=NOW,
    )
    service = SchedulerScheduleService(store)

    async def scenario() -> None:
        with pytest.raises(ScheduleFireLimitExceeded, match="exceeding limit"):
            await service.tick(
                workspace_id,
                through=Instant("2026-09-12T10:03:00.000000Z"),
                now=NOW,
                max_fires=2,
            )
        assert store.list_schedule_fires(workspace_id, schedule.id) == ()
        assert store.get_schedule_cursor(workspace_id, schedule.id) == Instant(
            "2026-09-12T10:00:00.000000Z"
        )

    asyncio.run(scenario())
