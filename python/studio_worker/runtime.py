"""Local SQLite + Docker worker runtime composition for the v0.1 execution path."""

from __future__ import annotations

import asyncio
import os
import signal
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic

from studio_core import RuntimeCapability, RuntimeCatalog, RuntimeProfile
from studio_execution import (
    DurableExecutionService,
    UnsupportedSchedulerWorkload,
    WorkerPollResult,
    execute_scheduler_job,
)
from studio_kernel import (
    ExecutionAttemptId,
    NotebookExecutionRequest,
    SessionPolicy,
)
from studio_orchestrator import (
    AttemptId,
    AttemptLimitExceeded,
    AttemptState,
    CellExecutionIdentity,
    ClaimedRun,
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
from studio_sql import SqlEngine
from studio_storage import (
    ArtifactStore,
    LocalArtifactStore,
    PostgresJobReadPort,
    S3ArtifactStore,
    SqliteJobStore,
)

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
    """Process-local configuration for one durable database/Docker worker."""

    paths: WorkerPaths
    owner: str
    image: str
    engine: str = "docker"
    limits: ContainerExecutionLimits = field(default_factory=ContainerExecutionLimits)
    database_name: str = "ronin.sqlite3"
    postgres_dsn: str | None = None
    lease_seconds: int = 30
    heartbeat_interval_seconds: float = 10.0
    poll_seconds: float = 1.0
    store_max_workers: int = 4
    store_max_in_flight: int = 8
    artifact_max_workers: int = 2
    artifact_max_in_flight: int = 4
    record_execution: Callable[[str, float, str], None] | None = None
    scheduler_sql_engine: SqlEngine | None = None
    scheduler_graph_adapter: object | None = None
    scheduler_quality_adapter: object | None = None
    connector_sync_service: object | None = None
    connector_connection: object | None = None
    connector_asset: object | None = None
    connector_secrets: object | None = None
    connector_destination: object | None = None
    notification_sink: object | None = None
    notification_artifacts: ArtifactStore | None = None
    ml_runner: object | None = None
    ml_lab: object | None = None
    ml_rows: object | None = None
    genai_runner: object | None = None
    semantic_refresh_runner: object | None = None

    def __post_init__(self) -> None:
        if not self.owner or self.owner != self.owner.strip():
            raise ValueError("worker owner must be non-empty and trimmed")
        if not self.database_name or Path(self.database_name).name != self.database_name:
            raise ValueError("worker database name must be one local filename")
        if self.postgres_dsn is not None and (
            not self.postgres_dsn or self.postgres_dsn != self.postgres_dsn.strip()
        ):
            raise ValueError("postgres_dsn must be non-empty and trimmed")
        if self.lease_seconds < 2:
            raise ValueError("lease_seconds must be at least 2")
        if not 0 < self.heartbeat_interval_seconds < self.lease_seconds:
            raise ValueError("heartbeat interval must be positive and shorter than the lease")
        if self.poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
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


def artifact_store_from_environment(config: LocalWorkerRuntimeConfig) -> ArtifactStore:
    """Build the configured artifact backend without silently degrading storage."""

    backend = os.environ.get("RONIN_ARTIFACT_BACKEND", "local").strip().casefold()
    if backend == "local":
        return LocalArtifactStore(config.artifact_root)
    if backend != "s3":
        raise ValueError("RONIN_ARTIFACT_BACKEND must be local or s3")
    bucket = os.environ.get("RONIN_S3_BUCKET", "").strip()
    if not bucket:
        raise ValueError("RONIN_S3_BUCKET is required when RONIN_ARTIFACT_BACKEND=s3")
    prefix = os.environ.get("RONIN_S3_PREFIX", "ronin/artifacts")
    return S3ArtifactStore(
        bucket,
        prefix=prefix,
        endpoint_url=os.environ.get("RONIN_S3_ENDPOINT_URL"),
        region_name=os.environ.get("RONIN_S3_REGION"),
    )


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
        artifact_store: ArtifactStore | None = None,
        now: Callable[[], Instant] = utc_now,
    ) -> None:
        self.config = config
        self._now = now
        self._policy = policy or SessionPolicy()
        self._runner = command_runner or AsyncioCommandRunner()
        self._engine_path = engine_path
        self._artifact_store = artifact_store or artifact_store_from_environment(config)
        config.paths.data_dir.mkdir(parents=True, exist_ok=True)
        store = (
            PostgresJobReadPort(config.postgres_dsn, application_name="ronin-worker")
            if config.postgres_dsn is not None
            else SqliteJobStore(config.database_path, migration_now=migration_now)
        )
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

    async def _poll(
        self,
        *,
        attempt_id: AttemptId,
        lease_token: LeaseToken,
    ) -> WorkerPollResult:
        return await self._service.worker_poll(
            owner=self.config.owner,
            lease_token=lease_token,
            attempt_id=attempt_id,
            lease_seconds=self.config.lease_seconds,
            now=self._now(),
        )

    async def _execute_claim(self, claim: ClaimedRun) -> WorkerExecutionOutcome:
        loop = asyncio.get_running_loop()
        if claim.job.target in {
            "sql.query",
            "graph.query",
            "quality.gate",
            "connector.sync",
            "notification.send",
            "ml.run",
            "genai.run",
            "semantic.refresh",
        }:
            if claim.job.target == "sql.query" and self.config.scheduler_sql_engine is None:
                raise UnsupportedSchedulerWorkload(
                    "sql.query scheduler execution requires scheduler_sql_engine"
                )
            if claim.job.target == "graph.query" and self.config.scheduler_graph_adapter is None:
                raise UnsupportedSchedulerWorkload(
                    "graph.query scheduler execution requires scheduler_graph_adapter"
                )
            if claim.job.target == "quality.gate" and self.config.scheduler_quality_adapter is None:
                raise UnsupportedSchedulerWorkload(
                    "quality.gate scheduler execution requires scheduler_quality_adapter"
                )
            if claim.job.target == "connector.sync" and self.config.connector_sync_service is None:
                raise UnsupportedSchedulerWorkload(
                    "connector.sync scheduler execution requires connector_sync_service"
                )
            if claim.job.target == "notification.send" and (
                self.config.notification_sink is None or self.config.notification_artifacts is None
            ):
                raise UnsupportedSchedulerWorkload(
                    "notification.send scheduler execution requires sink and artifacts"
                )
            if claim.job.target == "ml.run" and (
                self.config.ml_runner is None
                or self.config.ml_lab is None
                or self.config.ml_rows is None
            ):
                raise UnsupportedSchedulerWorkload(
                    "ml.run scheduler execution requires runner, lab, and rows"
                )
            if claim.job.target == "genai.run" and self.config.genai_runner is None:
                raise UnsupportedSchedulerWorkload(
                    "genai.run scheduler execution requires genai_runner"
                )
            if (
                claim.job.target == "semantic.refresh"
                and self.config.semantic_refresh_runner is None
            ):
                raise UnsupportedSchedulerWorkload(
                    "semantic.refresh scheduler execution requires semantic_refresh_runner"
                )
            try:
                result = await loop.run_in_executor(
                    self._preparation_executor,
                    lambda: execute_scheduler_job(
                        claim.job,
                        sql_engine=self.config.scheduler_sql_engine,
                        graph_adapter=self.config.scheduler_graph_adapter,
                        quality_adapter=self.config.scheduler_quality_adapter,
                        artifact_store=self._artifact_store,
                        workspace_id=claim.workspace_id,
                        run_id=str(claim.run.id),
                        now=self._now(),
                        connector_sync_service=self.config.connector_sync_service,
                        connector_connection=self.config.connector_connection,
                        connector_asset=self.config.connector_asset,
                        connector_secrets=self.config.connector_secrets,
                        connector_destination=self.config.connector_destination,
                        notification_sink=self.config.notification_sink,
                        notification_artifacts=self.config.notification_artifacts,
                        notification_now=self._now(),
                        ml_runner=self.config.ml_runner,
                        ml_lab=self.config.ml_lab,
                        ml_rows=self.config.ml_rows,
                        genai_runner=self.config.genai_runner,
                        semantic_refresh_runner=self.config.semantic_refresh_runner,
                    ),
                )
            except Exception:
                failure_code = (
                    "scheduler.sql.error"
                    if claim.job.target == "sql.query"
                    else "scheduler.graph.error"
                    if claim.job.target == "graph.query"
                    else "scheduler.quality.error"
                    if claim.job.target == "quality.gate"
                    else "scheduler.connector.error"
                    if claim.job.target == "connector.sync"
                    else "scheduler.notification.error"
                    if claim.job.target == "notification.send"
                    else "scheduler.ml.error"
                    if claim.job.target == "ml.run"
                    else "scheduler.genai.error"
                    if claim.job.target == "genai.run"
                    else "scheduler.semantic.error"
                )
                await self._service.worker_complete_attempt(
                    claim.attempt_id,
                    state=AttemptState.FAILED,
                    failure_code=failure_code,
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
                self._artifact_store,
                executor,
                self._policy,
                self.config.owner,
                lease_seconds=self.config.lease_seconds,
                heartbeat_interval_seconds=self.config.heartbeat_interval_seconds,
                now=self._now,
                artifact_max_workers=self.config.artifact_max_workers,
                artifact_max_in_flight=self.config.artifact_max_in_flight,
            )
            return await worker.run_scheduler_result(claim, result)
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
            self._artifact_store,
            executor,
            self._policy,
            self.config.owner,
            lease_seconds=self.config.lease_seconds,
            heartbeat_interval_seconds=self.config.heartbeat_interval_seconds,
            now=self._now,
            artifact_max_workers=self.config.artifact_max_workers,
            artifact_max_in_flight=self.config.artifact_max_in_flight,
        )
        return await worker.run(claim, request, identities)

    async def _abandon_claim(self, claim: ClaimedRun) -> None:
        """Release one live claim immediately while preserving fencing semantics."""

        try:
            await self._service.worker_complete_attempt(
                claim.attempt_id,
                state=AttemptState.ABANDONED,
                failure_code=None,
                owner=self.config.owner,
                lease_token=claim.lease_token,
                now=self._now(),
            )
        except (KeyError, ValueError):
            # A concurrently expired/lost lease is already fail-closed and reclaimable.
            return

    async def _wait_for_shutdown_or_poll(self, shutdown: asyncio.Event) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(shutdown.wait(), timeout=self.config.poll_seconds)

    async def run_once(
        self,
        *,
        attempt_id: AttemptId,
        lease_token: LeaseToken,
    ) -> LocalWorkerPollOutcome:
        """Reclaim expired work, claim at most one Run, then execute it to a safe boundary."""

        if self._closed:
            raise RuntimeError("local worker runtime is closed")
        polled = await self._poll(attempt_id=attempt_id, lease_token=lease_token)
        claim = polled.claim
        if claim is None:
            return LocalWorkerPollOutcome(polled.reclaimed_run_ids, None, None)

        started = monotonic()
        try:
            execution = await self._execute_claim(claim)
        except Exception:
            if self.config.record_execution is not None:
                self.config.record_execution("worker.execute", monotonic() - started, "failed")
            raise
        if self.config.record_execution is not None:
            self.config.record_execution("worker.execute", monotonic() - started, "succeeded")
        return LocalWorkerPollOutcome(
            polled.reclaimed_run_ids,
            claim.attempt_id,
            execution,
        )

    async def run_forever(self, shutdown: asyncio.Event) -> None:
        """Poll and execute serially until shutdown, releasing an active claim immediately."""

        if self._closed:
            raise RuntimeError("local worker runtime is closed")
        while not shutdown.is_set():
            attempt_id = AttemptId(f"attempt-{uuid.uuid4()}")
            lease_token = LeaseToken(f"lease-{uuid.uuid4()}")
            try:
                polled = await self._poll(attempt_id=attempt_id, lease_token=lease_token)
            except AttemptLimitExceeded:
                await self._wait_for_shutdown_or_poll(shutdown)
                continue

            claim = polled.claim
            if claim is None:
                await self._wait_for_shutdown_or_poll(shutdown)
                continue

            started = monotonic()
            execution = asyncio.create_task(self._execute_claim(claim))
            shutdown_wait = asyncio.create_task(shutdown.wait())
            try:
                done, _pending = await asyncio.wait(
                    {execution, shutdown_wait},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if shutdown_wait in done and shutdown.is_set() and not execution.done():
                    execution.cancel()
                    with suppress(asyncio.CancelledError):
                        await execution
                    await self._abandon_claim(claim)
                    return
                try:
                    await execution
                except Exception:
                    if self.config.record_execution is not None:
                        self.config.record_execution(
                            "worker.execute", monotonic() - started, "failed"
                        )
                    raise
                else:
                    if self.config.record_execution is not None:
                        self.config.record_execution(
                            "worker.execute", monotonic() - started, "succeeded"
                        )
            finally:
                shutdown_wait.cancel()
                with suppress(asyncio.CancelledError):
                    await shutdown_wait

    async def run_until_signalled(self) -> None:
        """Run continuously; first SIGINT/SIGTERM requests shutdown, second cancels immediately."""

        loop = asyncio.get_running_loop()
        shutdown = asyncio.Event()
        task = asyncio.current_task()
        installed: list[signal.Signals] = []

        def handle_signal() -> None:
            if shutdown.is_set():
                if task is not None:
                    task.cancel()
                return
            shutdown.set()

        signals: tuple[signal.Signals, signal.Signals] = (signal.SIGTERM, signal.SIGINT)
        for sig in signals:
            try:
                loop.add_signal_handler(sig, handle_signal)
            except (NotImplementedError, RuntimeError):
                continue
            installed.append(sig)
        try:
            await self.run_forever(shutdown)
        finally:
            for sig in installed:
                loop.remove_signal_handler(sig)


__all__ = (
    "LocalWorkerPollOutcome",
    "LocalWorkerRuntime",
    "LocalWorkerRuntimeConfig",
    "runtime_catalog_for_image",
)
