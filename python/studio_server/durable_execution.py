"""Async durable-execution composition for server and worker control paths."""

from __future__ import annotations

from dataclasses import dataclass

from studio_orchestrator import (
    AttemptId,
    ClaimedRun,
    Instant,
    Job,
    JobId,
    JobStore,
    LeaseToken,
    Run,
    RunId,
)
from studio_storage import BoundedAsyncJobStore


@dataclass(frozen=True, slots=True)
class WorkerPollResult:
    """One bounded worker maintenance/claim iteration."""

    reclaimed_run_ids: tuple[RunId, ...]
    claim: ClaimedRun | None


class DurableExecutionService:
    """Keep asyncio control paths behind one bounded durable-store boundary.

    The service deliberately contains no HTTP, Docker, SQLite, cloud, engine or
    provider semantics. It is the process-composition surface used by the future
    HTTP server and worker loop so those call sites cannot accidentally invoke the
    synchronous ``JobStore`` directly on an event-loop thread.
    """

    def __init__(
        self,
        store: JobStore,
        *,
        max_workers: int = 4,
        max_in_flight: int = 8,
    ) -> None:
        self._store = BoundedAsyncJobStore(
            store,
            max_workers=max_workers,
            max_in_flight=max_in_flight,
        )

    async def __aenter__(self) -> DurableExecutionService:
        return self

    async def __aexit__(
        self,
        _exc_type: object,
        _exc: object,
        _traceback: object,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._store.aclose()

    async def submit(self, job: Job, run: Run) -> Job:
        """Create or idempotently replay one durable job/run pair."""

        return await self._store.create_job(job, run)

    async def status(self, job_id: JobId) -> Job | None:
        """Read current durable job status without blocking the event loop."""

        return await self._store.get_job(job_id)

    async def cancel(self, job_id: JobId, *, now: Instant) -> Job:
        """Request cancellation through the same bounded store boundary."""

        return await self._store.request_cancel(job_id, now=now)

    async def worker_poll(
        self,
        *,
        owner: str,
        lease_token: LeaseToken,
        attempt_id: AttemptId,
        lease_seconds: int,
        now: Instant,
    ) -> WorkerPollResult:
        """Reclaim expired leases, then attempt one claim.

        Reclamation and claim remain separate ``JobStore`` operations so their
        existing transaction/fencing semantics stay authoritative. Backpressure is
        propagated to the caller; this method never spins or bypasses the bounded
        facade.
        """

        reclaimed = await self._store.reclaim_expired(now=now)
        claim = await self._store.claim_next_run(
            owner=owner,
            lease_token=lease_token,
            attempt_id=attempt_id,
            lease_seconds=lease_seconds,
            now=now,
        )
        return WorkerPollResult(reclaimed, claim)

    async def worker_heartbeat(
        self,
        attempt_id: AttemptId,
        *,
        owner: str,
        lease_token: LeaseToken,
        expires_at: Instant,
        now: Instant,
    ) -> bool:
        """Fence one worker heartbeat through the bounded durable-store facade."""

        return await self._store.heartbeat(
            attempt_id,
            owner=owner,
            lease_token=lease_token,
            expires_at=expires_at,
            now=now,
        )


__all__ = ("DurableExecutionService", "WorkerPollResult")
