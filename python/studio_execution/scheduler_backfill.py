"""Bounded snapshot-safe generation of scheduler backfill workflow runs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from studio_core import WorkspaceId
from studio_orchestrator import Instant
from studio_storage.scheduler_backfill import BackfillId, BackfillRun
from studio_storage.scheduler_backfill_runtime import (
    BackfillCapacityExhausted,
    SchedulerBackfillRuntimeStore,
)

from .scheduler_cron import evaluated_minutes, schedule_matches


@dataclass(frozen=True, slots=True)
class BackfillTickResult:
    fires: tuple[BackfillRun, ...]
    active_runs: int
    generation_complete: bool


def _instant_datetime(value: Instant | str) -> datetime:
    return datetime.strptime(
        str(Instant(value)), "%Y-%m-%dT%H:%M:%S.%fZ"
    ).replace(tzinfo=UTC)


def _minute_instant(value: datetime) -> Instant:
    return Instant(value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:00.000000Z"))


def _previous_minute(value: Instant | str) -> Instant:
    return _minute_instant(_instant_datetime(value) - timedelta(minutes=1))


def _bounded_through(cursor: Instant, end_at: Instant, max_scan_minutes: int) -> Instant:
    candidate = _minute_instant(
        _instant_datetime(cursor) + timedelta(minutes=max_scan_minutes)
    )
    return end_at if end_at < candidate else candidate


class SchedulerBackfillService:
    """Generate bounded historical schedule fires without touching cron cursors."""

    def __init__(self, store: SchedulerBackfillRuntimeStore) -> None:
        self._store = store

    async def tick(
        self,
        workspace_id: WorkspaceId,
        backfill_id: BackfillId,
        *,
        now: Instant | str,
        max_scan_minutes: int = 1440,
        max_new_runs: int = 100,
    ) -> BackfillTickResult:
        if max_scan_minutes < 1:
            raise ValueError("max_scan_minutes must be positive")
        if max_new_runs < 1:
            raise ValueError("max_new_runs must be positive")
        plan = await asyncio.to_thread(
            self._store.get_backfill_plan,
            workspace_id,
            backfill_id,
        )
        if plan is None:
            raise KeyError(str(backfill_id))
        active = await asyncio.to_thread(
            self._store.count_active_backfill_runs,
            workspace_id,
            backfill_id,
        )
        if plan.request.state == "cancelled":
            return BackfillTickResult((), active, plan.generation_complete)
        if plan.request.state == "completed":
            return BackfillTickResult((), active, True)
        if plan.generation_complete:
            if active == 0:
                await asyncio.to_thread(
                    self._store.complete_backfill,
                    workspace_id,
                    backfill_id,
                    now=now,
                )
            return BackfillTickResult((), active, True)

        cursor = plan.cursor_at or _previous_minute(plan.request.start_at)
        through = _bounded_through(cursor, plan.request.end_at, max_scan_minutes)
        minutes = evaluated_minutes(
            cursor=cursor,
            through=through,
            max_scan_minutes=max_scan_minutes,
        )
        existing_runs = {
            run.logical_time: run
            for run in await asyncio.to_thread(
                self._store.list_backfill_runs,
                workspace_id,
                backfill_id,
            )
        }
        available = min(max_new_runs, max(plan.max_concurrency - active, 0))
        created: list[BackfillRun] = []
        processed: Instant | None = None
        for minute in minutes:
            if schedule_matches(plan.schedule_snapshot, minute):
                existing = existing_runs.get(minute)
                if existing is not None:
                    if existing.state == "reserved":
                        recovered = await asyncio.to_thread(
                            self._store.create_snapshot_backfill_run,
                            workspace_id,
                            backfill_id,
                            logical_time=minute,
                            now=now,
                        )
                        existing_runs[minute] = recovered
                    processed = minute
                    continue
                if available == 0:
                    break
                try:
                    run = await asyncio.to_thread(
                        self._store.create_snapshot_backfill_run,
                        workspace_id,
                        backfill_id,
                        logical_time=minute,
                        now=now,
                    )
                except BackfillCapacityExhausted:
                    break
                existing_runs[minute] = run
                created.append(run)
                available -= 1
            processed = minute

        generation_complete = False
        if processed is not None:
            generation_complete = processed == plan.request.end_at
            plan = await asyncio.to_thread(
                self._store.advance_backfill_cursor,
                workspace_id,
                backfill_id,
                through=processed,
                generation_complete=generation_complete,
                now=now,
            )
        active = await asyncio.to_thread(
            self._store.count_active_backfill_runs,
            workspace_id,
            backfill_id,
        )
        if generation_complete and active == 0:
            await asyncio.to_thread(
                self._store.complete_backfill,
                workspace_id,
                backfill_id,
                now=now,
            )
        return BackfillTickResult(tuple(created), active, plan.generation_complete)


__all__ = ("BackfillTickResult", "SchedulerBackfillService")
