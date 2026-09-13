"""Application service for restart-safe scheduler task timeout enforcement."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from studio_orchestrator import Instant, JobState
from studio_storage.scheduler_controller import SchedulerControllerStore
from studio_storage.scheduler_timeout import (
    clear_timeout_request,
    finalize_timed_out_attempt,
    list_timeout_requests,
    request_overdue_timeouts,
)

from .scheduler_dispatch import DurableJobService


@dataclass(frozen=True, slots=True)
class SchedulerTimeoutCycle:
    detected: int
    cancellation_requests: int
    finalized: int


async def enforce_task_timeouts(
    store: SchedulerControllerStore,
    service: DurableJobService,
    *,
    now: Instant | str,
    limit: int = 100,
) -> SchedulerTimeoutCycle:
    """Persist timeout intent, cancel linked Jobs, and finalize terminal timeouts."""

    current = Instant(now)
    detected = await asyncio.to_thread(
        request_overdue_timeouts,
        store,
        now=current,
        limit=limit,
    )
    pending = await asyncio.to_thread(list_timeout_requests, store, limit=limit)
    cancellations = 0
    finalized = 0
    for request in pending:
        if request.job_id is None:
            if await asyncio.to_thread(
                finalize_timed_out_attempt,
                store,
                request,
                now=current,
            ):
                finalized += 1
            continue

        job = await service.status(request.job_id)
        if job is None:
            if await asyncio.to_thread(
                finalize_timed_out_attempt,
                store,
                request,
                now=current,
            ):
                finalized += 1
            continue
        if job.state in {JobState.SUCCEEDED, JobState.FAILED}:
            # The Job won the timeout race and reached a real terminal result first.
            # Drop the timeout marker so ordinary terminal reconciliation owns truth.
            await asyncio.to_thread(
                clear_timeout_request,
                store,
                request.workspace_id,
                request.task_attempt_id,
            )
            continue
        if job.state is JobState.CANCELLED:
            if await asyncio.to_thread(
                finalize_timed_out_attempt,
                store,
                request,
                now=current,
            ):
                finalized += 1
            continue
        if job.state is not JobState.CANCELLING:
            job = await service.cancel(request.job_id, now=current)
            cancellations += 1
        if job.state is JobState.CANCELLED:
            if await asyncio.to_thread(
                finalize_timed_out_attempt,
                store,
                request,
                now=current,
            ):
                finalized += 1

    return SchedulerTimeoutCycle(len(detected), cancellations, finalized)


__all__ = ("SchedulerTimeoutCycle", "enforce_task_timeouts")
