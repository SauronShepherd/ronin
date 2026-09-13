"""Application service for durable backfill group cancellation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from studio_core import WorkspaceId
from studio_orchestrator import Instant
from studio_storage.scheduler_backfill import BackfillId
from studio_storage.scheduler_backfill_runtime import SchedulerBackfillRuntimeStore

from .scheduler_cancellation import CancellableJobService, cancel_workflow_run


@dataclass(frozen=True, slots=True)
class BackfillCancellationResult:
    workflow_runs_seen: int
    jobs_cancelled: int


async def cancel_backfill_group(
    store: SchedulerBackfillRuntimeStore,
    service: CancellableJobService,
    workspace_id: WorkspaceId,
    backfill_id: BackfillId,
    *,
    now: Instant | str,
) -> BackfillCancellationResult:
    """Stop future backfill generation, then cancel every created child workflow run.

    The parent backfill state is persisted first. Repeating the call after interruption
    is safe because backfill cancellation and workflow cancellation are idempotent.
    Reserved-but-uncreated logical fires remain historical reservations and cannot be
    promoted after the parent backfill reaches the cancelled state.
    """

    current = Instant(now)
    await asyncio.to_thread(
        store.cancel_backfill,
        workspace_id,
        backfill_id,
        now=current,
    )
    runs = await asyncio.to_thread(store.list_backfill_runs, workspace_id, backfill_id)
    created = tuple(run for run in runs if run.state == "created")
    jobs_cancelled = 0
    for run in created:
        jobs_cancelled += await cancel_workflow_run(
            store,
            service,
            workspace_id,
            run.workflow_run_id,
            now=current,
        )
    return BackfillCancellationResult(len(created), jobs_cancelled)


__all__ = ("BackfillCancellationResult", "cancel_backfill_group")
