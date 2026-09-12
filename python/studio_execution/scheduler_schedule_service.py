"""Bounded durable cron schedule evaluation over scheduler fire/cursor state."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from studio_orchestrator import Instant
from studio_storage.scheduler_schedule import (
    Schedule,
    ScheduleFire,
    SchedulerScheduleStore,
    WorkspaceId,
)

from .scheduler_cron import evaluated_minutes, schedule_matches


@dataclass(frozen=True, slots=True)
class ScheduleTickResult:
    fires: tuple[ScheduleFire, ...]
    schedules_evaluated: int


class ScheduleFireLimitExceeded(RuntimeError):
    """Raised before mutation when one tick would create too many workflow runs."""


class SchedulerScheduleService:
    """Evaluate current/missed cron minutes with durable cursors and fire identity."""

    def __init__(self, store: SchedulerScheduleStore) -> None:
        self._store = store

    async def tick(
        self,
        workspace_id: WorkspaceId,
        *,
        through: Instant | str,
        now: Instant | str,
        max_scan_minutes: int = 1440,
        max_fires: int = 100,
    ) -> ScheduleTickResult:
        if max_fires < 1:
            raise ValueError("max_fires must be positive")
        schedules = await asyncio.to_thread(self._store.list_schedules, workspace_id)
        evaluation: list[tuple[Schedule, tuple[Instant, ...], tuple[Instant, ...]]] = []
        total_fires = 0
        for schedule in schedules:
            cursor = await asyncio.to_thread(
                self._store.get_schedule_cursor,
                workspace_id,
                schedule.id,
            )
            minutes = evaluated_minutes(
                cursor=cursor,
                through=through,
                max_scan_minutes=max_scan_minutes,
            )
            due = (
                tuple(minute for minute in minutes if schedule_matches(schedule, minute))
                if schedule.enabled
                else ()
            )
            total_fires += len(due)
            evaluation.append((schedule, minutes, due))

        if total_fires > max_fires:
            raise ScheduleFireLimitExceeded(
                f"schedule tick would create {total_fires} fires, exceeding limit {max_fires}"
            )

        fires: list[ScheduleFire] = []
        for schedule, minutes, due in evaluation:
            for logical_time in due:
                fire = await asyncio.to_thread(
                    self._store.fire_schedule,
                    workspace_id,
                    schedule.id,
                    scheduled_for=logical_time,
                    now=now,
                )
                fires.append(fire)
            # Advance only after every due fire in this evaluated interval has
            # been durably recorded. Crash-before-cursor retry is idempotent.
            if minutes:
                await asyncio.to_thread(
                    self._store.advance_schedule_cursor,
                    workspace_id,
                    schedule.id,
                    through=minutes[-1],
                    now=now,
                )
        return ScheduleTickResult(
            tuple(
                sorted(
                    fires,
                    key=lambda fire: (str(fire.scheduled_for), str(fire.schedule_id)),
                )
            ),
            len(schedules),
        )


__all__ = (
    "ScheduleFireLimitExceeded",
    "ScheduleTickResult",
    "SchedulerScheduleService",
)
