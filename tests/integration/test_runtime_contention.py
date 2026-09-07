from __future__ import annotations

import asyncio
import time
from pathlib import Path
from threading import Event

from studio_orchestrator import (
    AttemptId,
    Instant,
    Job,
    JobId,
    JobState,
    LeaseToken,
    Run,
    RunId,
    RunState,
)
from studio_server import DurableExecutionService
from studio_storage import (
    ArtifactRef,
    BoundedAsyncArtifactStore,
    LocalArtifactStore,
    SqliteJobStore,
)

NOW = Instant("2026-09-07T05:00:00.000000Z")
HEARTBEAT_NOW = Instant("2026-09-07T05:00:10.000000Z")
EXPIRY = Instant("2026-09-07T05:00:40.000000Z")


def _job(job_id: str, key: str) -> Job:
    return Job(
        id=JobId(job_id),
        project_id="examples/demo",
        idempotency_key=key,
        request_digest=("a" if job_id == "job-1" else "b") * 64,
        state=JobState.QUEUED,
        created_at=NOW,
        updated_at=NOW,
    )


def _run(run_id: str, job_id: str) -> Run:
    return Run(
        id=RunId(run_id),
        job_id=JobId(job_id),
        ordinal=1,
        state=RunState.PENDING,
        not_before=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


class _SlowStatusSqliteStore(SqliteJobStore):
    def __init__(self, path: Path) -> None:
        super().__init__(path, migration_now=NOW)
        self.status_started = Event()
        self.release_status = Event()

    def get_job(self, job_id: JobId) -> Job | None:
        if job_id == JobId("slow-status"):
            self.status_started.set()
            if not self.release_status.wait(timeout=5.0):
                raise RuntimeError("slow status call was not released")
        return super().get_job(job_id)


class _SlowArtifactStore(LocalArtifactStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.put_started = Event()
        self.release_put = Event()

    def put_bytes(
        self,
        *,
        role: str,
        data: bytes,
        media_type: str | None = None,
    ) -> ArtifactRef:
        if role == "slow":
            self.put_started.set()
            if not self.release_put.wait(timeout=5.0):
                raise RuntimeError("slow artifact put was not released")
        return super().put_bytes(role=role, data=data, media_type=media_type)


def test_real_sqlite_and_artifact_boundaries_preserve_unrelated_progress(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = _SlowStatusSqliteStore(tmp_path / "ronin.db")
        store.create_job(_job("job-1", "key-1"), _run("run-1", "job-1"))
        artifacts = _SlowArtifactStore(tmp_path / "artifacts")
        existing_ref = artifacts.put_bytes(role="existing", data=b"verified")

        async with DurableExecutionService(store, max_workers=2, max_in_flight=4) as service:
            claim = await service.worker_poll(
                owner="worker-1",
                lease_token=LeaseToken("lease-1"),
                attempt_id=AttemptId("attempt-1"),
                lease_seconds=30,
                now=NOW,
            )
            assert claim.claim is not None

            blocked_status = asyncio.create_task(service.status(JobId("slow-status")))
            assert await asyncio.to_thread(store.status_started.wait, 1.0)

            started = time.monotonic()
            assert await service.worker_heartbeat(
                AttemptId("attempt-1"),
                owner="worker-1",
                lease_token=LeaseToken("lease-1"),
                expires_at=EXPIRY,
                now=HEARTBEAT_NOW,
            )
            heartbeat_elapsed = time.monotonic() - started
            assert heartbeat_elapsed < 0.5

            store.release_status.set()
            assert await blocked_status is None

        async with BoundedAsyncArtifactStore(
            artifacts,
            max_workers=2,
            max_in_flight=4,
        ) as async_artifacts:
            blocked_put = asyncio.create_task(
                async_artifacts.put_bytes(role="slow", data=b"blocked")
            )
            assert await asyncio.to_thread(artifacts.put_started.wait, 1.0)

            started = time.monotonic()
            assert await async_artifacts.verify(existing_ref)
            verify_elapsed = time.monotonic() - started
            assert verify_elapsed < 0.5

            artifacts.release_put.set()
            slow_ref = await blocked_put
            assert await async_artifacts.verify(slow_ref)

    asyncio.run(scenario())
