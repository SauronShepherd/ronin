"""Bounded durable cron schedule evaluation over scheduler fire/cursor state."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from studio_core import Schedule, WorkspaceId
from studio_orchestrator import Instant
from studio_storage.scheduler_schedule import (
    ScheduleFire,
    SchedulerScheduleStore,
)

from .scheduler_cron import (
    CronExpression,
    CronSyntaxError,
    _instant_datetime,
    _minute_instant,
    evaluated_minutes,
    schedule_matches,
)

AuthorityCheck = Callable[[Instant | str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ScheduleTickResult:
    fires: tuple[ScheduleFire, ...]
    schedules_evaluated: int


class ScheduleFireLimitExceeded(RuntimeError):
    """Raised before mutation when one tick would create too many workflow runs."""


class SchedulerScheduleService:
    """Evaluate current/missed cron minutes with durable cursors and fire identity."""

    def __init__(
        self,
        store: SchedulerScheduleStore,
        *,
        authority_check: AuthorityCheck | None = None,
    ) -> None:
        self._store = store
        self._authority_check = authority_check

    async def _check_authority(self, now: Instant | str) -> None:
        if self._authority_check is not None:
            await self._authority_check(now)

    @staticmethod
    def preview_next_runs(
        schedule: Schedule,
        *,
        after: Instant | str,
        count: int = 10,
        max_scan_minutes: int = 100_000,
    ) -> tuple[Instant, ...]:
        """Preview future fire times without touching durable cursor state."""
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 1000:
            raise ValueError("preview count must be between 1 and 1000")
        if (
            not isinstance(max_scan_minutes, int)
            or isinstance(max_scan_minutes, bool)
            or max_scan_minutes < count
            or max_scan_minutes > 1_000_000
        ):
            raise ValueError("preview max_scan_minutes is outside the configured bound")
        if not schedule.enabled:
            return ()
        try:
            timezone = ZoneInfo(schedule.timezone)
        except ZoneInfoNotFoundError as exc:
            raise CronSyntaxError(f"unknown schedule timezone: {schedule.timezone}") from exc
        expression = CronExpression.parse(schedule.cron)
        start = _instant_datetime(after)
        candidate = start.replace(second=0, microsecond=0) + timedelta(minutes=1)
        result: list[Instant] = []
        for _ in range(max_scan_minutes):
            minute = _minute_instant(candidate)
            if expression.matches_local(_instant_datetime(minute).astimezone(timezone)):
                result.append(minute)
                if len(result) == count:
                    break
            candidate += timedelta(minutes=1)
        return tuple(result)

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
                await self._check_authority(now)
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
                await self._check_authority(now)
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
    "AuthorityCheck",
    "ScheduleFireLimitExceeded",
    "ScheduleTickResult",
    "SchedulerScheduleService",
)
