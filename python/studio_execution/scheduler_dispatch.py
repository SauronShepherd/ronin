"""Application services for dispatching/reconciling scheduler execution intents."""

from __future__ import annotations

import asyncio
from typing import Protocol

from studio_orchestrator import Instant, Job, JobId, Run
from studio_storage.scheduler_execution import (
    SchedulerExecutionLinkStore,
    TaskExecutionIntent,
)


class DurableJobService(Protocol):
    async def submit(self, job: Job, run: Run) -> Job: ...

    async def status(self, job_id: JobId) -> Job | None: ...


async def dispatch_execution_intent(
    intent: TaskExecutionIntent,
    service: DurableJobService,
) -> Job:
    """Idempotently submit the durable Job represented by one scheduler outbox row."""

    stored = await service.submit(intent.job, intent.run)
    if stored.id != intent.job.id or stored.request_digest != intent.job.request_digest:
        raise RuntimeError("durable execution service returned conflicting scheduler job identity")
    return stored


async def reconcile_execution_intent(
    intent: TaskExecutionIntent,
    service: DurableJobService,
    scheduler: SchedulerExecutionLinkStore,
    *,
    now: Instant | str,
) -> bool:
    """Reconcile the linked Job's terminal state back into scheduler task state."""

    job = await service.status(intent.job.id)
    if job is None:
        return False
    return await asyncio.to_thread(
        scheduler.reconcile_execution,
        intent.workspace_id,
        intent.task_attempt_id,
        job,
        now=now,
    )


__all__ = (
    "DurableJobService",
    "dispatch_execution_intent",
    "reconcile_execution_intent",
)
