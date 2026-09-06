"""Local SQLite + Docker worker runtime composition for the v0.1 execution path."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from studio_core import RuntimeCapability, RuntimeCatalog, RuntimeProfile
from studio_kernel import (
    ExecutionAttemptId,
    NotebookExecutionRequest,
    SessionPolicy,
)
from studio_orchestrator import (
    AttemptId,
    AttemptState,
    CellExecutionIdentity,
    Instant,
    Job,
    LeaseToken,
    RunId,
)
from studio_runners import (
    AsyncioCommandRunner,
    CancellableCommandRunner,
    ContainerExecutionLimits,
    ContainerExecutorConfig,
    DockerContainerKernelExecutor,
    LocalExecutionEvidenceStore,
)
from studio_server import DurableExecutionService
from studio_storage import LocalArtifactStore, SqliteJobStore

from .execution import DurableWorkerExecution, WorkerExecutionOutcome, utc_now
from .preparation import (
    LOCAL_DOCKER_PROFILE,
    WorkerPaths,
    build_request,
    execution_identities,
    load_project,
    resolve_runtime_snapshot,
)


@dataclass(frozen=True, slots=True)
class LocalWorkerRuntimeConfig:
    """Process-local configuration for one durable SQLite/Docker worker."""

    paths: WorkerPaths
    owner: str
    image: str
    engine: str = "docker"
    limits: ContainerExecutionLimits = field(default_factory=ContainerExecutionLimits)
    database_name: str = "ronin.sqlite3"
    lease_seconds: int = 30
    heartbeat_interval_seconds: float = 10.0
    store_max_workers: int = 4
    store_max_in_flight: int = 8
    artifact_max_workers: int = 2
    artifact_max_in_flight: int = 4

    def __post_init__(self) -> None:
        if not self.owner or self.owner != self.owner.strip():
            raise ValueError("worker owner must be non-empty and trimmed")
        if not self.database_name or Path(self.database_name).name != self.database_name:
            raise ValueError("worker database name must be one local filename")
        if self.lease_seconds < 2:
            raise ValueError("lease_seconds must be at least 2")
        if not 0 < self.heartbeat_interval_seconds < self.lease_seconds:
            raise ValueError("heartbeat interval must be positive and shorter than the lease")
        if self.store_max_workers < 1 or self.store_max_in_flight < self.store_max_workers:
            raise ValueError("invalid bounded JobStore executor limits")
        if self.artifact_max_workers < 1 or self.artifact_max_in_flight < self.artifact_max_workers:
            raise ValueError("invalid bounded artifact executor limits")
        ContainerExecutorConfig(image=self.image, limits=self.limits, engine=self.engine)

    @property
    def database_path(self) -> Path:
        return self.paths.data_dir / self.database_name

    @property
    def artifact_root(self) -> Path:
        return self.paths.data_dir / "artifacts"

    @property
    def execution_evidence_root(self) -> Path:
        return self.paths.data_dir / "execution-evidence"


@dataclass(frozen=True, slots=True)
class LocalWorkerPollOutcome:
    """Result of one reclaim/claim/execute iteration."""

    reclaimed_run_ids: tuple[RunId, ...]
    attempt_id: AttemptId | None
    execution: WorkerExecutionOutcome | None


def runtime_catalog_for_image(image: str) -> RuntimeCatalog:
    """Bind the logical local Docker profile to the exact immutable execution image."""

    profile = RuntimeProfile(
        LOCAL_DOCKER_PROFILE.ref,
        LOCAL_DOCKER_PROFILE.capabilities + (RuntimeCapability("execution-image", image),),
    )
    return RuntimeCatalog((profile,))


class LocalWorkerRuntime:
    """Own one bounded durable worker process composition.

    Filesystem/Git preparation is serialized on a dedicated executor because it performs
    blocking local I/O and revision capture. Durable store and artifact calls retain their
    own bounded async facades. Docker remains behind ``KernelCellExecutor``.
    """

    def __init__(
        self,
        config: LocalWorkerRuntimeConfig,
        *,
        migration_now: Instant,
        policy: SessionPolicy | None = None,
        command_runner: CancellableCommandRunner | None = None,
        engine_path: str | None = None,
        now: Callable[[], Instant] = utc_now,
    ) -> None:
        self.config = config
        self._now = now
        self._policy = policy or SessionPolicy()
        self._runner = command_runner or AsyncioCommandRunner()
        self._engine_path = engine_path
        config.paths.data_dir.mkdir(parents=True, exist_ok=True)
        store = SqliteJobStore(config.database_path, migration_now=migration_now)
        self._service = DurableExecutionService(
            store,
            max_workers=config.store_max_workers,
            max_in_flight=config.store_max_in_flight,
        )
        self._preparation_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="ronin-worker-prepare",
        )
        self._closed = False

    async def __aenter__(self) -> LocalWorkerRuntime:
        return self

    async def __aexit__(
        self,
        _exc_type: object,
        _exc: object,
        _traceback: object,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._service.aclose()
        self._preparation_executor.shutdown(wait=True, cancel_futures=True)

    def _prepare(
        self,
        claim_attempt: AttemptId,
        run_id: RunId,
        job: Job,
    ) -> tuple[NotebookExecutionRequest, tuple[CellExecutionIdentity, ...]]:
        loaded = load_project(self.config.paths, job)
        runtime = resolve_runtime_snapshot(
            loaded.manifest,
            runtime_catalog_for_image(self.config.image),
        )
        request = build_request(loaded, runtime, claim_attempt)
        identities = execution_identities(
            request,
            run_id=run_id,
            loaded=loaded,
            job=job,
        )
        return request, identities

    async def run_once(
        self,
        *,
        attempt_id: AttemptId,
        lease_token: LeaseToken,
    ) -> LocalWorkerPollOutcome:
        """Reclaim expired work, claim at most one Run, then execute it to a safe boundary."""

        if self._closed:
            raise RuntimeError("local worker runtime is closed")
        poll_now = self._now()
        polled = await self._service.worker_poll(
            owner=self.config.owner,
            lease_token=lease_token,
            attempt_id=attempt_id,
            lease_seconds=self.config.lease_seconds,
            now=poll_now,
        )
        claim = polled.claim
        if claim is None:
            return LocalWorkerPollOutcome(polled.reclaimed_run_ids, None, None)

        loop = asyncio.get_running_loop()
        try:
            request, identities = await loop.run_in_executor(
                self._preparation_executor,
                self._prepare,
                claim.attempt_id,
                claim.run.id,
                claim.job,
            )
        except Exception:
            await self._service.worker_complete_attempt(
                claim.attempt_id,
                state=AttemptState.FAILED,
                failure_code="worker.preparation.error",
                owner=self.config.owner,
                lease_token=claim.lease_token,
                now=self._now(),
            )
            raise

        executor = DockerContainerKernelExecutor(
            ContainerExecutorConfig(
                image=self.config.image,
                limits=self.config.limits,
                engine=self.config.engine,
            ),
            ExecutionAttemptId(str(claim.attempt_id)),
            LocalExecutionEvidenceStore(self.config.execution_evidence_root),
            runner=self._runner,
            engine_path=self._engine_path,
        )
        worker = DurableWorkerExecution(
            self._service,
            LocalArtifactStore(self.config.artifact_root),
            executor,
            self._policy,
            self.config.owner,
            lease_seconds=self.config.lease_seconds,
            heartbeat_interval_seconds=self.config.heartbeat_interval_seconds,
            now=self._now,
            artifact_max_workers=self.config.artifact_max_workers,
            artifact_max_in_flight=self.config.artifact_max_in_flight,
        )
        execution = await worker.run(claim, request, identities)
        return LocalWorkerPollOutcome(
            polled.reclaimed_run_ids,
            claim.attempt_id,
            execution,
        )


__all__ = (
    "LocalWorkerPollOutcome",
    "LocalWorkerRuntime",
    "LocalWorkerRuntimeConfig",
    "runtime_catalog_for_image",
)
