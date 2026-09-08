from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from pathlib import Path

from studio_core import ProjectManifest, RuntimeCatalog
from studio_execution import DurableExecutionService
from studio_kernel import (
    CancellationSignal,
    CellExecutionRequest,
    CellExecutionResult,
    ExecutorIsolation,
    NotebookExecutionRequest,
    RepositoryRevision,
    SessionPolicy,
)
from studio_notebook import NotebookDocument
from studio_orchestrator import (
    AttemptId,
    AttemptState,
    CellExecutionIdentity,
    Instant,
    Job,
    JobId,
    JobState,
    LeaseToken,
    Run,
    RunId,
    RunState,
)
from studio_storage import InMemoryJobStore, LocalArtifactStore
from studio_worker import (
    LOCAL_DOCKER_PROFILE,
    DurableWorkerExecution,
    LoadedProject,
    build_request,
    execution_identities,
    resolve_runtime_snapshot,
)

NOW = Instant("2026-09-08T05:00:00.000000Z")
ISOLATION = ExecutorIsolation(
    mode="container",
    dedicated_identity=True,
    network_isolated=True,
    filesystem_isolated=True,
    qualification_status="tested",
    qualification_scheme="ronin-test",
    qualification_version="1",
    runtime_identity="fake-runtime",
    evidence_ref="test://isolation",
)
POLICY = SessionPolicy()


def _job() -> Job:
    return Job(
        id=JobId("job-inflight-cancel"),
        project_id="examples/demo",
        idempotency_key="inflight-cancel-key",
        request_digest="a" * 64,
        state=JobState.QUEUED,
        created_at=NOW,
        updated_at=NOW,
        target="notebooks/etl.ronin.json",
        parameters_json="{}",
    )


def _run() -> Run:
    return Run(
        id=RunId("run-inflight-cancel"),
        job_id=JobId("job-inflight-cancel"),
        ordinal=1,
        state=RunState.PENDING,
        not_before=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def _prepared(
    attempt_id: AttemptId,
) -> tuple[NotebookExecutionRequest, tuple[CellExecutionIdentity, ...]]:
    project_dir = Path("examples/demo")
    manifest = ProjectManifest.from_json(
        (project_dir / ".ronin" / "project.json").read_text(encoding="utf-8")
    )
    document = NotebookDocument.from_json(
        (project_dir / "notebooks" / "etl.ronin.json").read_text(encoding="utf-8")
    )
    loaded = LoadedProject(
        manifest=manifest,
        document=document,
        revision=RepositoryRevision("b" * 40, "c" * 64),
        project_dir=project_dir.resolve(),
    )
    runtime = resolve_runtime_snapshot(manifest, RuntimeCatalog((LOCAL_DOCKER_PROFILE,)))
    request = build_request(loaded, runtime, attempt_id)
    identities = execution_identities(
        request,
        run_id=RunId("run-inflight-cancel"),
        loaded=loaded,
        job=_job(),
    )
    return replace(request, cells=request.cells[:1]), identities[:1]


@dataclass
class _EventControlledExecutor:
    started: asyncio.Event
    release: asyncio.Event
    cancellation_seen: bool = False

    @property
    def isolation(self) -> ExecutorIsolation:
        return ISOLATION

    async def execute(
        self,
        cell: CellExecutionRequest,
        cancellation: CancellationSignal,
    ) -> CellExecutionResult:
        self.started.set()
        await self.release.wait()
        self.cancellation_seen = cancellation.is_cancelled
        state = "cancelled" if self.cancellation_seen else "succeeded"
        return CellExecutionResult(cell.cell_id, state)


class _ObservedCancellationService(DurableExecutionService):
    def __init__(self, store: InMemoryJobStore, observed: asyncio.Event) -> None:
        super().__init__(store)
        self._observed = observed

    async def status(self, job_id: JobId) -> Job | None:
        job = await super().status(job_id)
        if job is not None and job.state in {JobState.CANCELLING, JobState.CANCELLED}:
            self._observed.set()
        return job


def test_worker_cancels_executor_while_cell_is_in_flight(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = InMemoryJobStore()
        cancellation_observed = asyncio.Event()
        poll_now = asyncio.Event()

        async def controlled_poll_wait(_seconds: float) -> None:
            await poll_now.wait()
            poll_now.clear()

        async with _ObservedCancellationService(store, cancellation_observed) as service:
            await service.submit(_job(), _run())
            polled = await service.worker_poll(
                owner="worker-1",
                lease_token=LeaseToken("lease-inflight-cancel"),
                attempt_id=AttemptId("attempt-inflight-cancel"),
                lease_seconds=30,
                now=NOW,
            )
            assert polled.claim is not None
            request, identities = _prepared(AttemptId("attempt-inflight-cancel"))
            started = asyncio.Event()
            release = asyncio.Event()
            executor = _EventControlledExecutor(started, release)
            worker = DurableWorkerExecution(
                service,
                LocalArtifactStore(tmp_path / "artifacts"),
                executor,
                POLICY,
                "worker-1",
                heartbeat_interval_seconds=29,
                now=lambda: NOW,
                _cancellation_wait=controlled_poll_wait,
            )

            task = asyncio.create_task(worker.run(polled.claim, request, identities))
            await asyncio.wait_for(started.wait(), timeout=1)
            assert not task.done()
            cancelled = await service.cancel(JobId("job-inflight-cancel"), now=NOW)
            assert cancelled is not None
            assert cancelled.state is JobState.CANCELLING

            poll_now.set()
            await asyncio.wait_for(cancellation_observed.wait(), timeout=1)
            release.set()
            outcome = await asyncio.wait_for(task, timeout=1)

            assert executor.cancellation_seen is True
            assert outcome.state is AttemptState.CANCELLED
            assert outcome.executed_cell_ids == (identities[0].cell_id,)
            job = await service.status(JobId("job-inflight-cancel"))
            assert job is not None
            assert job.state is JobState.CANCELLED
            events = store.read_events(RunId("run-inflight-cancel"), since=0)
            assert events[-1].kind == "worker.attempt.cancelled"

    asyncio.run(scenario())
