"""Bounded non-blocking composition for synchronous job-store implementations."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import TypeVar

from studio_orchestrator import (
    AttemptId,
    AttemptState,
    ClaimedRun,
    Instant,
    Job,
    JobId,
    JobState,
    JobStore,
    LeaseToken,
    Page,
    Run,
    RunId,
    StoredCellResult,
    StoredEvidenceRef,
    StoredExecutionEvent,
)

_T = TypeVar("_T")


class StorageBackpressureError(RuntimeError):
    """Raised when bounded storage execution capacity is already exhausted."""


class BoundedAsyncJobStore:
    """Run whole synchronous ``JobStore`` operations outside an asyncio event loop.

    The wrapper owns a dedicated bounded executor. ``max_in_flight`` covers both
    running and executor-queued operations; once that capacity is exhausted new
    calls fail immediately with ``StorageBackpressureError`` instead of joining an
    unbounded executor queue.

    Cancelling an awaiting coroutine does not cancel a synchronous operation that
    may already be mutating durable state. Its capacity slot remains reserved until
    the underlying call actually finishes, preserving the bound and leaving
    transaction/fencing semantics inside the wrapped ``JobStore`` implementation.
    """

    def __init__(
        self,
        store: JobStore,
        *,
        max_workers: int = 4,
        max_in_flight: int = 8,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        if max_in_flight < max_workers:
            raise ValueError("max_in_flight must be greater than or equal to max_workers")
        self._store = store
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="ronin-job-store",
        )
        self._capacity_lock = asyncio.Lock()
        self._available_slots = max_in_flight
        self._closed = False

    async def __aenter__(self) -> BoundedAsyncJobStore:
        return self

    async def __aexit__(
        self,
        _exc_type: object,
        _exc: object,
        _traceback: object,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Stop accepting work and shut down the dedicated executor off-loop."""

        if self._closed:
            return
        self._closed = True
        await asyncio.to_thread(self._executor.shutdown, wait=True, cancel_futures=False)

    async def create_job(self, job: Job, run: Run) -> Job:
        return await self._call(partial(self._store.create_job, job, run))

    async def get_job(self, job_id: JobId) -> Job | None:
        return await self._call(partial(self._store.get_job, job_id))

    async def list_jobs(
        self,
        *,
        project_id: str | None,
        state: JobState | None,
        limit: int,
        cursor: str | None,
    ) -> Page:
        return await self._call(
            partial(
                self._store.list_jobs,
                project_id=project_id,
                state=state,
                limit=limit,
                cursor=cursor,
            )
        )

    async def request_cancel(self, job_id: JobId, *, now: Instant) -> Job:
        return await self._call(partial(self._store.request_cancel, job_id, now=now))

    async def claim_next_run(
        self,
        *,
        owner: str,
        lease_token: LeaseToken,
        attempt_id: AttemptId,
        lease_seconds: int,
        now: Instant,
    ) -> ClaimedRun | None:
        return await self._call(
            partial(
                self._store.claim_next_run,
                owner=owner,
                lease_token=lease_token,
                attempt_id=attempt_id,
                lease_seconds=lease_seconds,
                now=now,
            )
        )

    async def heartbeat(
        self,
        attempt_id: AttemptId,
        *,
        owner: str,
        lease_token: LeaseToken,
        expires_at: Instant,
        now: Instant,
    ) -> bool:
        return await self._call(
            partial(
                self._store.heartbeat,
                attempt_id,
                owner=owner,
                lease_token=lease_token,
                expires_at=expires_at,
                now=now,
            )
        )

    async def append_events(
        self,
        attempt_id: AttemptId,
        events: Sequence[StoredExecutionEvent],
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant,
    ) -> None:
        await self._call(
            partial(
                self._store.append_events,
                attempt_id,
                events,
                owner=owner,
                lease_token=lease_token,
                now=now,
            )
        )

    async def read_events(
        self,
        run_id: RunId,
        *,
        since: int,
    ) -> tuple[StoredExecutionEvent, ...]:
        return await self._call(partial(self._store.read_events, run_id, since=since))

    async def put_cell_result(
        self,
        attempt_id: AttemptId,
        result: StoredCellResult,
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant,
    ) -> None:
        await self._call(
            partial(
                self._store.put_cell_result,
                attempt_id,
                result,
                owner=owner,
                lease_token=lease_token,
                now=now,
            )
        )

    async def read_cell_results(self, run_id: RunId) -> tuple[StoredCellResult, ...]:
        return await self._call(partial(self._store.read_cell_results, run_id))

    async def put_evidence(
        self,
        attempt_id: AttemptId,
        ref: StoredEvidenceRef,
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant,
    ) -> None:
        await self._call(
            partial(
                self._store.put_evidence,
                attempt_id,
                ref,
                owner=owner,
                lease_token=lease_token,
                now=now,
            )
        )

    async def read_evidence(self, run_id: RunId) -> tuple[StoredEvidenceRef, ...]:
        return await self._call(partial(self._store.read_evidence, run_id))

    async def complete_attempt(
        self,
        attempt_id: AttemptId,
        *,
        state: AttemptState,
        failure_code: str | None,
        owner: str,
        lease_token: LeaseToken,
        now: Instant,
    ) -> None:
        await self._call(
            partial(
                self._store.complete_attempt,
                attempt_id,
                state=state,
                failure_code=failure_code,
                owner=owner,
                lease_token=lease_token,
                now=now,
            )
        )

    async def reclaim_expired(self, *, now: Instant) -> tuple[RunId, ...]:
        return await self._call(partial(self._store.reclaim_expired, now=now))

    async def _reserve_slot(self) -> None:
        async with self._capacity_lock:
            if self._closed:
                raise RuntimeError("job-store executor is closed")
            if self._available_slots == 0:
                raise StorageBackpressureError("job-store execution capacity exhausted")
            self._available_slots -= 1

    def _release_slot(self, _future: object) -> None:
        self._available_slots += 1

    async def _call(self, operation: Callable[[], _T]) -> _T:
        await self._reserve_slot()
        loop = asyncio.get_running_loop()
        try:
            future = loop.run_in_executor(self._executor, operation)
        except BaseException:
            self._available_slots += 1
            raise
        future.add_done_callback(self._release_slot)
        return await asyncio.shield(future)


__all__ = ("BoundedAsyncJobStore", "StorageBackpressureError")
