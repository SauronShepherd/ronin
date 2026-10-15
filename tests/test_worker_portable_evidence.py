from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from studio_core import ProjectManifest, RuntimeCatalog
from studio_kernel import (
    CancellationSignal,
    CellExecutionRequest,
    CellExecutionResult,
    ExecutionEvidenceReference,
    ExecutorIsolation,
    RepositoryRevision,
    SessionPolicy,
)
from studio_notebook import NotebookDocument
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
from studio_storage import InMemoryJobStore, LocalArtifactStore
from studio_worker import (
    LOCAL_DOCKER_PROFILE,
    DurableWorkerExecution,
    LoadedProject,
    WorkerExecutionError,
    build_request,
    execution_identities,
    resolve_runtime_snapshot,
)

NOW = Instant("2026-09-07T18:10:00.000000Z")
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


def _job() -> Job:
    return Job(
        id=JobId("job-portable-evidence"),
        project_id="examples/demo",
        idempotency_key="portable-evidence-key",
        request_digest="a" * 64,
        state=JobState.QUEUED,
        created_at=NOW,
        updated_at=NOW,
        target="notebooks/etl.ronin.json",
        parameters_json="{}",
    )


def _run() -> Run:
    return Run(
        id=RunId("run-portable-evidence"),
        job_id=JobId("job-portable-evidence"),
        ordinal=1,
        state=RunState.PENDING,
        not_before=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def _prepared(attempt_id: AttemptId):
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
        run_id=RunId("run-portable-evidence"),
        loaded=loaded,
        job=_job(),
    )
    return replace(request, cells=request.cells[:1]), identities[:1]


async def _claim(service: DurableExecutionService):
    polled = await service.worker_poll(
        owner="worker-evidence",
        lease_token=LeaseToken("lease-portable-evidence"),
        attempt_id=AttemptId("attempt-portable-evidence"),
        lease_seconds=30,
        now=NOW,
    )
    assert polled.claim is not None
    return polled.claim


@dataclass
class _PortableEvidenceExecutor:
    portable: bool = True

    @property
    def isolation(self) -> ExecutorIsolation:
        return ISOLATION

    async def execute(
        self,
        cell: CellExecutionRequest,
        cancellation: CancellationSignal,
    ) -> CellExecutionResult:
        assert not cancellation.is_cancelled
        if not self.portable:
            return CellExecutionResult(
                cell.cell_id,
                "succeeded",
                evidence=(ExecutionEvidenceReference("log", "legacy://opaque"),),
            )
        return CellExecutionResult(
            cell.cell_id,
            "succeeded",
            evidence=(
                ExecutionEvidenceReference(
                    "log",
                    "local-evidence://attempt/cell/log.json",
                    "sha256",
                    "1" * 64,
                    "application/vnd.ronin.execution-evidence+json",
                    101,
                ),
                ExecutionEvidenceReference(
                    "resource",
                    "local-evidence://attempt/cell/resource.json",
                    "sha256",
                    "2" * 64,
                    "application/vnd.ronin.execution-evidence+json",
                    202,
                ),
            ),
        )


def test_runner_evidence_is_first_class_durable_and_location_independent(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = InMemoryJobStore()
        async with DurableExecutionService(store) as service:
            await service.submit(_job(), _run())
            claim = await _claim(service)
            request, identities = _prepared(AttemptId("attempt-portable-evidence"))
            worker = DurableWorkerExecution(
                service,
                LocalArtifactStore(tmp_path / "artifacts"),
                _PortableEvidenceExecutor(),
                SessionPolicy(),
                "worker-evidence",
                now=lambda: NOW,
            )

            outcome = await worker.run(claim, request, identities)
            assert outcome.executed_cell_ids == (identities[0].cell_id,)

            evidence = await service.worker_read_evidence(RunId("run-portable-evidence"))
            by_role = {ref.role: ref for ref in evidence}
            assert set(by_role) == {"log", "resource", "cell-result"}
            assert by_role["log"].cell_id == identities[0].cell_id
            assert by_role["log"].portable_identity == (
                "log",
                "sha256",
                "1" * 64,
                "application/vnd.ronin.execution-evidence+json",
                101,
            )
            assert by_role["resource"].portable_identity == (
                "resource",
                "sha256",
                "2" * 64,
                "application/vnd.ronin.execution-evidence+json",
                202,
            )
            assert by_role["log"].storage_ref == "local-evidence://attempt/cell/log.json"

            result = (await service.worker_read_cell_results(RunId("run-portable-evidence")))[0]
            assert (
                '"digest":"1111111111111111111111111111111111111111111111111111111111111111"'
                in result.result_json
            )
            assert '"availability":"available"' in result.result_json
            assert '"locator":"local-evidence://attempt/cell/log.json"' in result.result_json

    asyncio.run(scenario())


def test_durable_worker_rejects_opaque_runner_evidence_before_checkpoint(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = InMemoryJobStore()
        async with DurableExecutionService(store) as service:
            await service.submit(_job(), _run())
            claim = await _claim(service)
            request, identities = _prepared(AttemptId("attempt-portable-evidence"))
            worker = DurableWorkerExecution(
                service,
                LocalArtifactStore(tmp_path / "artifacts"),
                _PortableEvidenceExecutor(portable=False),
                SessionPolicy(),
                "worker-evidence",
                now=lambda: NOW,
            )

            with pytest.raises(WorkerExecutionError, match="requires portable execution evidence"):
                await worker.run(claim, request, identities)
            assert await service.worker_read_cell_results(RunId("run-portable-evidence")) == ()
            assert await service.worker_read_evidence(RunId("run-portable-evidence")) == ()

    asyncio.run(scenario())
