"""Application service for durable workflow cancellation propagation."""

from __future__ import annotations

import asyncio
from typing import Protocol

from studio_core import WorkflowRunId, WorkspaceId
from studio_orchestrator import Instant, Job, JobId
from studio_storage.scheduler_cancellation import (
    cancel_unsubmitted_execution,
    request_workflow_cancellation,
)
from studio_storage.scheduler_execution import SchedulerExecutionLinkStore


class CancellableJobService(Protocol):
    """Minimal Job control surface needed by scheduler cancellation."""

    async def status(self, job_id: JobId) -> Job | None: ...

    async def cancel(self, job_id: JobId, *, now: Instant) -> Job: ...


async def cancel_workflow_run(
    store: SchedulerExecutionLinkStore,
    service: CancellableJobService,
    workspace_id: WorkspaceId,
    workflow_run_id: WorkflowRunId,
    *,
    now: Instant | str,
) -> int:
    """Persist workflow cancellation, then cancel or retire linked executions.

    Scheduler state is written first. For each published intent, the durable JobStore
    decides whether a Job exists. Missing Jobs are retired from the scheduler outbox;
    existing Jobs receive the normal Job cancellation request. Repeating the call is
    safe after interruption because both branches are idempotent.
    """

    current = Instant(now)
    job_ids = await asyncio.to_thread(
        request_workflow_cancellation,
        store,
        workspace_id,
        workflow_run_id,
        now=current,
    )
    cancelled_jobs = 0
    for job_id in job_ids:
        job = await service.status(job_id)
        if job is None:
            await asyncio.to_thread(
                cancel_unsubmitted_execution,
                store,
                workspace_id,
                job_id,
                now=current,
            )
            continue
        await service.cancel(job_id, now=current)
        cancelled_jobs += 1
    return cancelled_jobs


__all__ = ("CancellableJobService", "cancel_workflow_run")
