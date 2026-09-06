from __future__ import annotations

import asyncio
from threading import Event, get_ident
from typing import cast

from studio_orchestrator import (
    AttemptId,
    Instant,
    Job,
    JobId,
    JobState,
    JobStore,
    LeaseToken,
    Run,
    RunId,
    RunState,
)
from studio_server import DurableExecutionService
from studio_storage import InMemoryJobStore

NOW = Instant("2026-09-06T09:00:00.000000Z")
HEARTBEAT = Instant("2026-09-06T09:00:10.000000Z")
EXPIRY = Instant("2026-09-06T09:00:40.000000Z")
AFTER_EXPIRY = Instant("2026-09-06T09:00:41.000000Z")


def _job() -> Job:
    return Job(
        id=JobId("job-1"),
        project_id="project-1",
        idempotency_key="key-1",
        request_digest="a" * 64,
        state=JobState.QUEUED,
        created_at=NOW,
        updated_at=NOW,
    )


def _run() -> Run:
    return Run(
        id=RunId("run-1"),
        job_id=JobId("job-1"),
        ordinal=1,
        state=RunState.PENDING,
        not_before=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def test_submit_status_worker_claim_heartbeat_and_reclaim_use_one_async_boundary() -> None:
    async def scenario() -> None:
        store = InMemoryJobStore()
        async with DurableExecutionService(store, max_workers=2, max_in_flight=4) as service:
            created = await service.submit(_job(), _run())
            assert created.id == JobId("job-1")
            assert await service.status(JobId("job-1")) == created

            first = await service.worker_poll(
                owner="worker-1",
                lease_token=LeaseToken("lease-1"),
                attempt_id=AttemptId("attempt-1"),
                lease_seconds=30,
                now=NOW,
            )
            assert first.reclaimed_run_ids == ()
            assert first.claim is not None
            assert first.claim.run.id == RunId("run-1")
            assert first.claim.attempt_ordinal == 1

            assert await service.worker_heartbeat(
                AttemptId("attempt-1"),
                owner="worker-1",
                lease_token=LeaseToken("lease-1"),
                expires_at=EXPIRY,
                now=HEARTBEAT,
            )

            replacement = await service.worker_poll(
                owner="worker-2",
                lease_token=LeaseToken("lease-2"),
                attempt_id=AttemptId("attempt-2"),
                lease_seconds=30,
                now=AFTER_EXPIRY,
            )
            assert replacement.reclaimed_run_ids == (RunId("run-1"),)
            assert replacement.claim is not None
            assert replacement.claim.run.id == RunId("run-1")
            assert replacement.claim.attempt_ordinal == 2

    asyncio.run(scenario())


class _ContendedStore:
    def __init__(self) -> None:
        self.status_started = Event()
        self.release_status = Event()
        self.status_thread_id: int | None = None
        self.heartbeat_thread_id: int | None = None

    def get_job(self, _job_id: JobId) -> None:
        self.status_thread_id = get_ident()
        self.status_started.set()
        if not self.release_status.wait(timeout=5):
            raise RuntimeError("test status call was not released")

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
            and expires_at == EXPIRY
            and now == HEARTBEAT
        )


def test_blocked_status_does_not_stall_worker_heartbeat() -> None:
    store = _ContendedStore()

    async def scenario() -> None:
        event_loop_thread = get_ident()
        async with DurableExecutionService(
            cast(JobStore, store),
            max_workers=2,
            max_in_flight=2,
        ) as service:
            blocked_status = asyncio.create_task(service.status(JobId("job-1")))
            assert await asyncio.to_thread(store.status_started.wait, 1)

            heartbeat = await asyncio.wait_for(
                service.worker_heartbeat(
                    AttemptId("attempt-1"),
                    owner="worker-1",
                    lease_token=LeaseToken("lease-1"),
                    expires_at=EXPIRY,
                    now=HEARTBEAT,
                ),
                timeout=0.25,
            )
            assert heartbeat
            assert store.status_thread_id is not None
            assert store.heartbeat_thread_id is not None
            assert store.status_thread_id != event_loop_thread
            assert store.heartbeat_thread_id != event_loop_thread

            store.release_status.set()
            assert await blocked_status is None

    asyncio.run(scenario())
