"""Application service for durable workflow cancellation propagation."""

from __future__ import annotations

import asyncio
from typing import Protocol

from studio_core import WorkflowRunId, WorkspaceId
from studio_orchestrator import Instant, JobId
from studio_storage.scheduler_cancellation import request_workflow_cancellation
from studio_storage.scheduler_execution import SchedulerExecutionLinkStore


class CancellableJobService(Protocol):
    """Minimal structural protocol implemented by DurableExecutionService."""

    async def cancel(self, job_id: JobId, *, now: Instant): ...


async def cancel_workflow_run(
    store: SchedulerExecutionLinkStore,
    service: CancellableJobService,
    workspace_id: WorkspaceId,
    workflow_run_id: WorkflowRunId,
    *,
    now: Instant | str,
) -> int:
    """Persist workflow cancellation, then request cancellation of linked Jobs.

    The durable scheduler state is written first. If the process fails while sending
    Job cancellation requests, callers can safely invoke this function again; the
    storage transition returns the same still-running linked Job identities.
    """

    current = Instant(now)
    job_ids = await asyncio.to_thread(
        request_workflow_cancellation,
        store,
        workspace_id,
        workflow_run_id,
        now=current,
    )
    for job_id in job_ids:
        await service.cancel(job_id, now=current)
    return len(job_ids)


__all__ = ("CancellableJobService", "cancel_workflow_run")
