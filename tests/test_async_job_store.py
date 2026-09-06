from __future__ import annotations

import asyncio
from threading import Event, get_ident
from typing import cast

import pytest
from studio_orchestrator import AttemptId, Instant, JobId, JobStore, LeaseToken
from studio_storage.async_store import BoundedAsyncJobStore, StorageBackpressureError


class _BlockingStore:
    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()
        self.worker_thread_id: int | None = None
        self.heartbeat_thread_id: int | None = None

    def get_job(self, _job_id: JobId) -> None:
        self.worker_thread_id = get_ident()
        self.started.set()
        if not self.release.wait(timeout=5):
            raise RuntimeError("test store was not released")
        return None

    def heartbeat(
        self,
        _attempt_id: AttemptId,
        *,
        owner: str,
        lease_token: LeaseToken,
        expires_at: Instant,
        now: Instant,
    ) -> bool:
        self.heartbeat_thread_id = get_ident()
        return (
            owner == "worker-1"
            and lease_token == LeaseToken("lease-1")
            and expires_at == Instant("2026-09-06T09:00:30.000000Z")
            and now == Instant("2026-09-06T09:00:10.000000Z")
        )


def _async_store(
    store: _BlockingStore,
    *,
    max_workers: int,
    max_in_flight: int,
) -> BoundedAsyncJobStore:
    return BoundedAsyncJobStore(
        cast(JobStore, store),
        max_workers=max_workers,
        max_in_flight=max_in_flight,
    )


def test_blocking_store_io_does_not_stall_event_loop() -> None:
    store = _BlockingStore()

    async def scenario() -> None:
        loop_thread_id = get_ident()
        async with _async_store(store, max_workers=1, max_in_flight=1) as async_store:
            task = asyncio.create_task(async_store.get_job(JobId("job-1")))
            await asyncio.to_thread(store.started.wait, 1)

            ticks = 0
            for _ in range(5):
                await asyncio.sleep(0)
                ticks += 1

            assert ticks == 5
            assert store.worker_thread_id is not None
            assert store.worker_thread_id != loop_thread_id
            store.release.set()
            assert await task is None

    asyncio.run(scenario())


def test_heartbeat_progresses_while_unrelated_store_io_is_blocked() -> None:
    store = _BlockingStore()

    async def scenario() -> None:
        loop_thread_id = get_ident()
        async with _async_store(store, max_workers=2, max_in_flight=2) as async_store:
            blocked = asyncio.create_task(async_store.get_job(JobId("job-1")))
            await asyncio.to_thread(store.started.wait, 1)

            heartbeat = await asyncio.wait_for(
                async_store.heartbeat(
                    AttemptId("attempt-1"),
                    owner="worker-1",
                    lease_token=LeaseToken("lease-1"),
                    expires_at=Instant("2026-09-06T09:00:30.000000Z"),
                    now=Instant("2026-09-06T09:00:10.000000Z"),
                ),
                timeout=0.25,
            )

            assert heartbeat is True
            assert store.heartbeat_thread_id is not None
            assert store.heartbeat_thread_id != loop_thread_id
            store.release.set()
            await blocked

    asyncio.run(scenario())


def test_capacity_exhaustion_fails_fast_without_unbounded_queueing() -> None:
    store = _BlockingStore()

    async def scenario() -> None:
        async with _async_store(store, max_workers=1, max_in_flight=1) as async_store:
            first = asyncio.create_task(async_store.get_job(JobId("job-1")))
            await asyncio.to_thread(store.started.wait, 1)

            with pytest.raises(StorageBackpressureError, match="capacity exhausted"):
                await async_store.get_job(JobId("job-2"))

            store.release.set()
            await first

    asyncio.run(scenario())


def test_cancellation_is_responsive_but_keeps_capacity_fenced_until_store_finishes() -> None:
    store = _BlockingStore()

    async def scenario() -> None:
        async with _async_store(store, max_workers=1, max_in_flight=1) as async_store:
            task = asyncio.create_task(async_store.get_job(JobId("job-1")))
            await asyncio.to_thread(store.started.wait, 1)

            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

            with pytest.raises(StorageBackpressureError, match="capacity exhausted"):
                await async_store.get_job(JobId("job-2"))

            store.release.set()
            for _ in range(100):
                await asyncio.sleep(0.001)
                try:
                    result = await async_store.get_job(JobId("job-3"))
                except StorageBackpressureError:
                    continue
                assert result is None
                break
            else:
                pytest.fail("capacity was not released after synchronous operation completed")

    asyncio.run(scenario())


def test_invalid_executor_bounds_and_closed_store_fail_closed() -> None:
    store = _BlockingStore()
    typed_store = cast(JobStore, store)

    with pytest.raises(ValueError, match="max_workers"):
        BoundedAsyncJobStore(typed_store, max_workers=0)
    with pytest.raises(ValueError, match="max_in_flight"):
        BoundedAsyncJobStore(typed_store, max_workers=2, max_in_flight=1)

    async def scenario() -> None:
        async_store = BoundedAsyncJobStore(typed_store, max_workers=1, max_in_flight=1)
        await async_store.aclose()
        await async_store.aclose()
        with pytest.raises(RuntimeError, match="closed"):
            await async_store.get_job(JobId("job-1"))

    asyncio.run(scenario())
