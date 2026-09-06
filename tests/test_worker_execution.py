from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from studio_core import ProjectManifest, RuntimeCatalog
from studio_kernel import (
    CancellationSignal,
    CellExecutionRequest,
    CellExecutionResult,
    ExecutionAttemptId,
    ExecutorIsolation,
    KernelDirective,
    NotebookExecutionRequest,
    RepositoryRevision,
    SessionPolicy,
)
from studio_notebook import CellId, NotebookDocument
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
from studio_server import DurableExecutionService
from studio_storage import InMemoryJobStore, LocalArtifactStore
from studio_worker import (
    LOCAL_DOCKER_PROFILE,
    DurableWorkerExecution,
    LoadedProject,
    WorkerExecutionError,
    WorkerLeaseLost,
    build_request,
    execution_identities,
    resolve_runtime_snapshot,
    utc_now,
)

NOW = Instant("2026-09-06T17:40:00.000000Z")
AFTER_EXPIRY = Instant("2026-09-06T17:40:31.000000Z")
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
        id=JobId("job-worker"),
        project_id="examples/demo",
        idempotency_key="worker-key",
        request_digest="a" * 64,
        state=JobState.QUEUED,
        created_at=NOW,
        updated_at=NOW,
        target="notebooks/etl.ronin.json",
        parameters_json='{"mode":"test"}',
    )


def _run() -> Run:
    return Run(
        id=RunId("run-worker"),
        job_id=JobId("job-worker"),
        ordinal=1,
        state=RunState.PENDING,
        not_before=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def _prepared(
    attempt_id: AttemptId,
    *,
    cells: int = 2,
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
        run_id=RunId("run-worker"),
        loaded=loaded,
        job=_job(),
    )
    return replace(request, cells=request.cells[:cells]), identities[:cells]


async def _claim(service: DurableExecutionService, attempt: str, lease: str):
    polled = await service.worker_poll(
        owner="worker-1",
        lease_token=LeaseToken(lease),
        attempt_id=AttemptId(attempt),
        lease_seconds=30,
        now=NOW,
    )
    assert polled.claim is not None
    return polled.claim


@dataclass
class _SuccessExecutor:
    store: InMemoryJobStore | None = None
    expected_first_id: str | None = None
    cancel_service: DurableExecutionService | None = None
    delay: float = 0.0
    calls: int = 0

    @property
    def isolation(self) -> ExecutorIsolation:
        return ISOLATION

    async def execute(
        self,
        cell: CellExecutionRequest,
        cancellation: CancellationSignal,
    ) -> CellExecutionResult:
        self.calls += 1
        if self.calls == 2 and self.store is not None:
            results = self.store.read_cell_results(RunId("run-worker"))
            evidence = self.store.read_evidence(RunId("run-worker"))
            assert self.expected_first_id is not None
            assert [result.cell_id for result in results] == [self.expected_first_id]
            assert evidence[-1].cell_id == self.expected_first_id
            assert evidence[-1].role == "cell-result"
        if self.calls == 1 and self.cancel_service is not None:
            await self.cancel_service.cancel(JobId("job-worker"), now=NOW)
        if self.delay:
            await asyncio.sleep(self.delay)
        assert not cancellation.is_cancelled
        return CellExecutionResult(cell.cell_id, "succeeded")


@dataclass
class _BlockingExecutor:
    started: asyncio.Event
    calls: int = 0

    @property
    def isolation(self) -> ExecutorIsolation:
        return ISOLATION

    async def execute(
        self,
        cell: CellExecutionRequest,
        cancellation: CancellationSignal,
    ) -> CellExecutionResult:
        self.calls += 1
        if self.calls == 1:
            return CellExecutionResult(cell.cell_id, "succeeded")
        self.started.set()
        blocker = asyncio.Event()
        while not cancellation.is_cancelled:
            with suppress(TimeoutError):
                await asyncio.wait_for(blocker.wait(), timeout=0.001)
        return CellExecutionResult(cell.cell_id, "cancelled")


class _FailingHeartbeatStore(InMemoryJobStore):
    def __init__(self) -> None:
        super().__init__()
        self.heartbeat_calls = 0

    def heartbeat(
        self,
        attempt_id: AttemptId,
        *,
        owner: str,
        lease_token: LeaseToken,
        expires_at: Instant | str,
        now: Instant | str,
    ) -> bool:
        del attempt_id, owner, lease_token, expires_at, now
        self.heartbeat_calls += 1
        return False


class _CountingHeartbeatStore(InMemoryJobStore):
    def __init__(self) -> None:
        super().__init__()
        self.heartbeat_calls = 0

    def heartbeat(
        self,
        attempt_id: AttemptId,
        *,
        owner: str,
        lease_token: LeaseToken,
        expires_at: Instant | str,
        now: Instant | str,
    ) -> bool:
        self.heartbeat_calls += 1
        return super().heartbeat(
            attempt_id,
            owner=owner,
            lease_token=lease_token,
            expires_at=expires_at,
            now=now,
        )


def _cell_ids(identities: tuple[CellExecutionIdentity, ...]) -> tuple[str, ...]:
    return tuple(identity.cell_id for identity in identities)


def test_worker_configuration_and_clock_are_fail_closed(tmp_path: Path) -> None:
    executor = _SuccessExecutor()
    store = InMemoryJobStore()
    service = DurableExecutionService(store)
    artifacts = LocalArtifactStore(tmp_path / "artifacts")
    with pytest.raises(ValueError, match="owner"):
        DurableWorkerExecution(service, artifacts, executor, POLICY, " bad ")
    with pytest.raises(ValueError, match="at least 2"):
        DurableWorkerExecution(service, artifacts, executor, POLICY, "worker-1", lease_seconds=1)
    with pytest.raises(ValueError, match="shorter"):
        DurableWorkerExecution(
            service,
            artifacts,
            executor,
            POLICY,
            "worker-1",
            heartbeat_interval_seconds=30,
        )
    with pytest.raises(ValueError, match="artifact_max_workers"):
        DurableWorkerExecution(
            service,
            artifacts,
            executor,
            POLICY,
            "worker-1",
            artifact_max_workers=0,
        )
    with pytest.raises(ValueError, match="artifact_max_in_flight"):
        DurableWorkerExecution(
            service,
            artifacts,
            executor,
            POLICY,
            "worker-1",
            artifact_max_workers=2,
            artifact_max_in_flight=1,
        )
    assert str(utc_now()).endswith("Z")
    asyncio.run(service.aclose())


def test_worker_rejects_mismatched_claim_inputs(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = InMemoryJobStore()
        async with DurableExecutionService(store) as service:
            await service.submit(_job(), _run())
            claim = await _claim(service, "attempt-1", "lease-1")
            request, identities = _prepared(AttemptId("attempt-1"), cells=1)
            worker = DurableWorkerExecution(
                service,
                LocalArtifactStore(tmp_path / "artifacts"),
                _SuccessExecutor(),
                POLICY,
                "worker-1",
                now=lambda: NOW,
            )
            with pytest.raises(WorkerExecutionError, match="counts"):
                await worker.run(claim, request, ())
            wrong_identity = replace(identities[0], run_id=RunId("other-run"))
            with pytest.raises(WorkerExecutionError, match="run does not match"):
                await worker.run(claim, request, (wrong_identity,))
            wrong_request = replace(request, attempt_id=ExecutionAttemptId("attempt-other"))
            with pytest.raises(WorkerExecutionError, match="attempt does not match"):
                await worker.run(claim, wrong_request, identities)

    asyncio.run(scenario())


def test_success_checkpoints_result_and_artifact_before_next_cell(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = InMemoryJobStore()
        async with DurableExecutionService(store) as service:
            await service.submit(_job(), _run())
            claim = await _claim(service, "attempt-1", "lease-1")
            request, identities = _prepared(AttemptId("attempt-1"))
            expected_ids = _cell_ids(identities)
            executor = _SuccessExecutor(store=store, expected_first_id=expected_ids[0])
            worker = DurableWorkerExecution(
                service,
                LocalArtifactStore(tmp_path / "artifacts"),
                executor,
                POLICY,
                "worker-1",
                now=lambda: NOW,
            )
            outcome = await worker.run(claim, request, identities)
            assert outcome.state is AttemptState.SUCCEEDED
            assert outcome.executed_cell_ids == expected_ids
            assert outcome.reused_cell_ids == ()
            assert executor.calls == 2
            job = await service.status(JobId("job-worker"))
            assert job is not None
            assert job.state is JobState.SUCCEEDED
            assert len(await service.worker_read_cell_results(RunId("run-worker"))) == 2
            assert len(await service.worker_read_evidence(RunId("run-worker"))) == 2
            events = store.read_events(RunId("run-worker"), since=0)
            assert [event.sequence for event in events] == list(range(len(events)))
            assert events[-1].kind == "worker.attempt.succeeded"

    asyncio.run(scenario())


def test_permission_denial_and_executor_exception_fail_attempt(tmp_path: Path) -> None:
    class ExplodingExecutor(_SuccessExecutor):
        async def execute(
            self,
            cell: CellExecutionRequest,
            cancellation: CancellationSignal,
        ) -> CellExecutionResult:
            del cell, cancellation
            raise RuntimeError("secret adapter detail")

    async def scenario(permission_denied: bool) -> None:
        store = InMemoryJobStore()
        async with DurableExecutionService(store) as service:
            await service.submit(_job(), _run())
            claim = await _claim(service, "attempt-1", "lease-1")
            request, identities = _prepared(AttemptId("attempt-1"), cells=1)
            executor: _SuccessExecutor = ExplodingExecutor()
            if permission_denied:
                first = replace(
                    request.cells[0],
                    directive=KernelDirective(
                        adapter_id="python",
                        kind="exec",
                        required_permissions=("workspace.write",),
                    ),
                )
                request = replace(request, cells=(first,))
                executor = _SuccessExecutor()
            artifact_dir = "permission" if permission_denied else "exception"
            worker = DurableWorkerExecution(
                service,
                LocalArtifactStore(tmp_path / artifact_dir),
                executor,
                POLICY,
                "worker-1",
                now=lambda: NOW,
            )
            outcome = await worker.run(claim, request, identities)
            assert outcome.state is AttemptState.FAILED
            expected = "kernel.permission.denied" if permission_denied else "kernel.executor.error"
            assert outcome.failure_code == expected
            result = (await service.worker_read_cell_results(RunId("run-worker")))[0]
            assert expected in result.result_json

    asyncio.run(scenario(True))
    asyncio.run(scenario(False))


def test_worker_rejects_executor_cell_identity_drift(tmp_path: Path) -> None:
    class DriftExecutor(_SuccessExecutor):
        async def execute(
            self,
            cell: CellExecutionRequest,
            cancellation: CancellationSignal,
        ) -> CellExecutionResult:
            del cell, cancellation
            return CellExecutionResult(CellId("wrong-cell"), "succeeded")

    async def scenario() -> None:
        store = InMemoryJobStore()
        async with DurableExecutionService(store) as service:
            await service.submit(_job(), _run())
            claim = await _claim(service, "attempt-1", "lease-1")
            request, identities = _prepared(AttemptId("attempt-1"), cells=1)
            worker = DurableWorkerExecution(
                service,
                LocalArtifactStore(tmp_path / "artifacts"),
                DriftExecutor(),
                POLICY,
                "worker-1",
                now=lambda: NOW,
            )
            with pytest.raises(WorkerExecutionError, match="changed cell identity"):
                await worker.run(claim, request, identities)
            assert store.read_cell_results(RunId("run-worker")) == ()

    asyncio.run(scenario())


def test_cancellation_is_polled_between_cells(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = InMemoryJobStore()
        async with DurableExecutionService(store) as service:
            await service.submit(_job(), _run())
            claim = await _claim(service, "attempt-1", "lease-1")
            request, identities = _prepared(AttemptId("attempt-1"))
            executor = _SuccessExecutor(cancel_service=service)
            worker = DurableWorkerExecution(
                service,
                LocalArtifactStore(tmp_path / "artifacts"),
                executor,
                POLICY,
                "worker-1",
                now=lambda: NOW,
            )
            outcome = await worker.run(claim, request, identities)
            assert outcome.state is AttemptState.CANCELLED
            assert outcome.executed_cell_ids == (_cell_ids(identities)[0],)
            assert executor.calls == 1
            job = await service.status(JobId("job-worker"))
            assert job is not None
            assert job.state is JobState.CANCELLED

    asyncio.run(scenario())


def test_lease_loss_cancels_active_execution_without_checkpoint_or_completion(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        store = _FailingHeartbeatStore()
        async with DurableExecutionService(store) as service:
            await service.submit(_job(), _run())
            claim = await _claim(service, "attempt-1", "lease-1")
            request, identities = _prepared(AttemptId("attempt-1"), cells=1)
            started = asyncio.Event()
            executor = _BlockingExecutor(started, calls=1)
            worker = DurableWorkerExecution(
                service,
                LocalArtifactStore(tmp_path / "artifacts"),
                executor,
                POLICY,
                "worker-1",
                heartbeat_interval_seconds=0.001,
                now=lambda: NOW,
            )
            with pytest.raises(WorkerLeaseLost, match="lease lost"):
                await asyncio.wait_for(worker.run(claim, request, identities), timeout=1)
            assert store.heartbeat_calls >= 1
            assert store.read_cell_results(RunId("run-worker")) == ()
            job = await service.status(JobId("job-worker"))
            assert job is not None
            assert job.state is JobState.RUNNING

    asyncio.run(scenario())


def test_heartbeat_task_is_cancelled_and_awaited_on_success(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = _CountingHeartbeatStore()
        async with DurableExecutionService(store) as service:
            await service.submit(_job(), _run())
            claim = await _claim(service, "attempt-1", "lease-1")
            request, identities = _prepared(AttemptId("attempt-1"), cells=1)
            worker = DurableWorkerExecution(
                service,
                LocalArtifactStore(tmp_path / "artifacts"),
                _SuccessExecutor(delay=0.02),
                POLICY,
                "worker-1",
                heartbeat_interval_seconds=0.005,
                now=lambda: NOW,
            )
            outcome = await worker.run(claim, request, identities)
            assert outcome.state is AttemptState.SUCCEEDED
            count = store.heartbeat_calls
            assert count >= 1
            await asyncio.sleep(0.02)
            assert store.heartbeat_calls == count

    asyncio.run(scenario())


def test_crash_reclaim_reuses_verified_checkpoint_in_same_run(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = InMemoryJobStore()
        artifacts = LocalArtifactStore(tmp_path / "artifacts")
        async with DurableExecutionService(store) as service:
            await service.submit(_job(), _run())
            first_claim = await _claim(service, "attempt-1", "lease-1")
            first_request, identities = _prepared(AttemptId("attempt-1"))
            expected_ids = _cell_ids(identities)
            started = asyncio.Event()
            first_worker = DurableWorkerExecution(
                service,
                artifacts,
                _BlockingExecutor(started),
                POLICY,
                "worker-1",
                heartbeat_interval_seconds=29,
                now=lambda: NOW,
            )
            task = asyncio.create_task(first_worker.run(first_claim, first_request, identities))
            await asyncio.wait_for(started.wait(), timeout=1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert [item.cell_id for item in store.read_cell_results(RunId("run-worker"))] == [
                expected_ids[0]
            ]

            replacement = await service.worker_poll(
                owner="worker-1",
                lease_token=LeaseToken("lease-2"),
                attempt_id=AttemptId("attempt-2"),
                lease_seconds=30,
                now=AFTER_EXPIRY,
            )
            assert replacement.reclaimed_run_ids == (RunId("run-worker"),)
            assert replacement.claim is not None
            second_request = replace(first_request, attempt_id=ExecutionAttemptId("attempt-2"))
            second_executor = _SuccessExecutor()
            second_worker = DurableWorkerExecution(
                service,
                artifacts,
                second_executor,
                POLICY,
                "worker-1",
                now=lambda: AFTER_EXPIRY,
            )
            outcome = await second_worker.run(replacement.claim, second_request, identities)
            assert outcome.state is AttemptState.SUCCEEDED
            assert outcome.reused_cell_ids == (expected_ids[0],)
            assert outcome.executed_cell_ids == (expected_ids[1],)
            assert second_executor.calls == 1
            events = store.read_events(RunId("run-worker"), since=0)
            assert any(event.kind == "worker.cell.reused" for event in events)

    asyncio.run(scenario())


def test_corrupt_checkpoint_artifact_forces_reexecution_after_reclaim(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = InMemoryJobStore()
        artifact_root = tmp_path / "artifacts"
        artifacts = LocalArtifactStore(artifact_root)
        async with DurableExecutionService(store) as service:
            await service.submit(_job(), _run())
            first_claim = await _claim(service, "attempt-1", "lease-1")
            first_request, identities = _prepared(AttemptId("attempt-1"))
            expected_ids = _cell_ids(identities)
            started = asyncio.Event()
            first_worker = DurableWorkerExecution(
                service,
                artifacts,
                _BlockingExecutor(started),
                POLICY,
                "worker-1",
                heartbeat_interval_seconds=29,
                now=lambda: NOW,
            )
            task = asyncio.create_task(first_worker.run(first_claim, first_request, identities))
            await asyncio.wait_for(started.wait(), timeout=1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

            ref = store.read_evidence(RunId("run-worker"))[-1]
            path = artifact_root / "sha256" / ref.digest[:2] / ref.digest
            path.write_bytes(b"corrupt")
            replacement = await service.worker_poll(
                owner="worker-1",
                lease_token=LeaseToken("lease-2"),
                attempt_id=AttemptId("attempt-2"),
                lease_seconds=30,
                now=AFTER_EXPIRY,
            )
            assert replacement.claim is not None
            second_request = replace(first_request, attempt_id=ExecutionAttemptId("attempt-2"))
            executor = _SuccessExecutor()
            worker = DurableWorkerExecution(
                service,
                artifacts,
                executor,
                POLICY,
                "worker-1",
                now=lambda: AFTER_EXPIRY,
            )
            outcome = await worker.run(replacement.claim, second_request, identities)
            assert outcome.reused_cell_ids == ()
            assert outcome.executed_cell_ids == expected_ids
            assert executor.calls == 2
            assert len(store.read_evidence(RunId("run-worker"))) == 3

    asyncio.run(scenario())
