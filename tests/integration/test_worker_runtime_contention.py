from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event

import pytest
import studio_worker.runtime as worker_runtime_module
from studio_kernel import CancellationSignal
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
from studio_runners import CommandOutcome
from studio_storage import ArtifactRef, LocalArtifactStore, SqliteJobStore
from studio_worker import LocalWorkerRuntime, LocalWorkerRuntimeConfig, WorkerPaths

OLD_NOW = Instant("2026-09-06T20:00:00.000000Z")
IMAGE = "sha256:" + "1" * 64


def _job() -> Job:
    return Job(
        id=JobId("job-contention"),
        project_id="examples/demo",
        idempotency_key="contention-key",
        request_digest="a" * 64,
        state=JobState.QUEUED,
        created_at=OLD_NOW,
        updated_at=OLD_NOW,
        target="notebooks/etl.ronin.json",
        parameters_json='{"mode":"contention"}',
    )


def _run() -> Run:
    return Run(
        id=RunId("run-contention"),
        job_id=JobId("job-contention"),
        ordinal=1,
        state=RunState.PENDING,
        not_before=OLD_NOW,
        created_at=OLD_NOW,
        updated_at=OLD_NOW,
    )


def _config(tmp_path: Path) -> LocalWorkerRuntimeConfig:
    config = LocalWorkerRuntimeConfig(
        paths=WorkerPaths(Path.cwd(), tmp_path),
        owner="worker-contention",
        image=IMAGE,
    )
    assert config.lease_seconds == 30
    assert config.heartbeat_interval_seconds == 10.0
    assert config.store_max_workers == 4
    assert config.store_max_in_flight == 8
    assert config.artifact_max_workers == 2
    assert config.artifact_max_in_flight == 4
    return config


def _seed(config: LocalWorkerRuntimeConfig) -> None:
    store = SqliteJobStore(config.database_path, migration_now=OLD_NOW)
    store.create_job(_job(), _run())


@dataclass
class _Runner:
    block_on_call: int | None = None
    started: asyncio.Event = field(default_factory=asyncio.Event)
    calls: int = 0

    async def run(
        self,
        args: tuple[str, ...],
        *,
        input_text: str,
        cancellation: CancellationSignal,
        timeout_seconds: float,
        cancellation_args: tuple[str, ...],
    ) -> CommandOutcome:
        del args, input_text, timeout_seconds, cancellation_args
        self.calls += 1
        if self.block_on_call == self.calls:
            self.started.set()
            await asyncio.Event().wait()
        assert not cancellation.is_cancelled
        return CommandOutcome(0, f"cell-{self.calls}", False, False, 1)


@dataclass
class _Clock:
    value: Instant

    def __call__(self) -> Instant:
        return self.value


class _SlowStatusSqliteStore(SqliteJobStore):
    def __init__(self, path: Path, *, migration_now: Instant) -> None:
        super().__init__(path, migration_now=migration_now)
        self.started = Event()
        self.release = Event()
        self._blocked = False

    def get_job(self, job_id: JobId) -> Job | None:
        if job_id == JobId("job-contention") and not self._blocked:
            self._blocked = True
            self.started.set()
            if not self.release.wait(timeout=20.0):
                raise RuntimeError("slow status contention was not released")
        return super().get_job(job_id)


class _SlowPutArtifactStore(LocalArtifactStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.started = Event()
        self.release = Event()
        self._blocked = False

    def put_bytes(
        self,
        *,
        role: str,
        data: bytes,
        media_type: str | None = None,
    ) -> ArtifactRef:
        if role == "cell-result" and not self._blocked:
            self._blocked = True
            self.started.set()
            if not self.release.wait(timeout=20.0):
                raise RuntimeError("slow artifact write contention was not released")
        return super().put_bytes(role=role, data=data, media_type=media_type)


class _SlowVerifyArtifactStore(LocalArtifactStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.started = Event()
        self.release = Event()
        self._blocked = False

    def verify(self, ref: ArtifactRef) -> bool:
        if not self._blocked:
            self._blocked = True
            self.started.set()
            if not self.release.wait(timeout=20.0):
                raise RuntimeError("slow artifact verification contention was not released")
        return super().verify(ref)


def _lease_state(database_path: Path, attempt_id: AttemptId) -> tuple[str, str]:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT heartbeat_at, lease_expires_at FROM attempts WHERE attempt_id=?",
            (str(attempt_id),),
        ).fetchone()
    assert row is not None
    heartbeat_at, lease_expires_at = row
    assert isinstance(heartbeat_at, str)
    assert isinstance(lease_expires_at, str)
    return heartbeat_at, lease_expires_at


async def _wait_for_durable_heartbeat(
    database_path: Path,
    attempt_id: AttemptId,
    previous_heartbeat: str,
    previous_expiry: str,
) -> tuple[str, str]:
    async with asyncio.timeout(15.0):
        while True:
            heartbeat_at, lease_expires_at = _lease_state(database_path, attempt_id)
            if heartbeat_at != previous_heartbeat:
                assert heartbeat_at > previous_heartbeat
                assert lease_expires_at > previous_expiry
                return heartbeat_at, lease_expires_at
            await asyncio.sleep(0.1)


def test_runtime_heartbeat_renews_during_real_sqlite_and_artifact_write_contention(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        config = _config(tmp_path)
        _seed(config)
        slow_store: _SlowStatusSqliteStore | None = None
        slow_artifacts: _SlowPutArtifactStore | None = None
        artifacts_created = asyncio.Event()

        def make_store(path: Path, *, migration_now: Instant) -> _SlowStatusSqliteStore:
            nonlocal slow_store
            slow_store = _SlowStatusSqliteStore(path, migration_now=migration_now)
            return slow_store

        def make_artifacts(root: Path) -> _SlowPutArtifactStore:
            nonlocal slow_artifacts
            slow_artifacts = _SlowPutArtifactStore(root)
            artifacts_created.set()
            return slow_artifacts

        monkeypatch.setattr(worker_runtime_module, "SqliteJobStore", make_store)
        monkeypatch.setattr(worker_runtime_module, "LocalArtifactStore", make_artifacts)

        attempt_id = AttemptId("attempt-contention-live")
        async with LocalWorkerRuntime(
            config,
            migration_now=OLD_NOW,
            command_runner=_Runner(),
            engine_path="docker",
        ) as runtime:
            assert slow_store is not None
            task = asyncio.create_task(
                runtime.run_once(
                    attempt_id=attempt_id,
                    lease_token=LeaseToken("lease-contention-live"),
                )
            )
            assert await asyncio.to_thread(slow_store.started.wait, 2.0)
            first_heartbeat, first_expiry = _lease_state(config.database_path, attempt_id)
            second_heartbeat, second_expiry = await _wait_for_durable_heartbeat(
                config.database_path,
                attempt_id,
                first_heartbeat,
                first_expiry,
            )
            slow_store.release.set()

            await asyncio.wait_for(artifacts_created.wait(), timeout=2.0)
            assert slow_artifacts is not None
            assert await asyncio.to_thread(slow_artifacts.started.wait, 2.0)
            await _wait_for_durable_heartbeat(
                config.database_path,
                attempt_id,
                second_heartbeat,
                second_expiry,
            )
            slow_artifacts.release.set()
            outcome = await asyncio.wait_for(task, timeout=5.0)

        assert outcome.execution is not None
        assert outcome.execution.state.value == "succeeded"
        assert len(outcome.execution.executed_cell_ids) == 6

    asyncio.run(scenario())


def test_runtime_reclaims_expired_attempt_and_renews_lease_during_artifact_verify_contention(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        config = _config(tmp_path)
        _seed(config)
        first_runner = _Runner(block_on_call=2)
        first_runtime = LocalWorkerRuntime(
            config,
            migration_now=OLD_NOW,
            command_runner=first_runner,
            engine_path="docker",
            now=_Clock(OLD_NOW),
        )
        first_task = asyncio.create_task(
            first_runtime.run_once(
                attempt_id=AttemptId("attempt-contention-old"),
                lease_token=LeaseToken("lease-contention-old"),
            )
        )
        await asyncio.wait_for(first_runner.started.wait(), timeout=2.0)
        first_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first_task
        await first_runtime.aclose()

        stored = SqliteJobStore(config.database_path, migration_now=OLD_NOW)
        assert len(stored.read_cell_results(RunId("run-contention"))) == 1

        slow_artifacts: _SlowVerifyArtifactStore | None = None
        artifacts_created = asyncio.Event()

        def make_artifacts(root: Path) -> _SlowVerifyArtifactStore:
            nonlocal slow_artifacts
            slow_artifacts = _SlowVerifyArtifactStore(root)
            artifacts_created.set()
            return slow_artifacts

        monkeypatch.setattr(worker_runtime_module, "LocalArtifactStore", make_artifacts)
        attempt_id = AttemptId("attempt-contention-replacement")
        async with LocalWorkerRuntime(
            config,
            migration_now=OLD_NOW,
            command_runner=_Runner(),
            engine_path="docker",
        ) as replacement:
            task = asyncio.create_task(
                replacement.run_once(
                    attempt_id=attempt_id,
                    lease_token=LeaseToken("lease-contention-replacement"),
                )
            )
            await asyncio.wait_for(artifacts_created.wait(), timeout=2.0)
            assert slow_artifacts is not None
            assert await asyncio.to_thread(slow_artifacts.started.wait, 2.0)
            first_heartbeat, first_expiry = _lease_state(config.database_path, attempt_id)
            await _wait_for_durable_heartbeat(
                config.database_path,
                attempt_id,
                first_heartbeat,
                first_expiry,
            )
            slow_artifacts.release.set()
            outcome = await asyncio.wait_for(task, timeout=5.0)

        assert outcome.reclaimed_run_ids == (RunId("run-contention"),)
        assert outcome.attempt_id == attempt_id
        assert outcome.execution is not None
        assert outcome.execution.state.value == "succeeded"
        assert len(outcome.execution.reused_cell_ids) == 1
        assert len(outcome.execution.executed_cell_ids) == 5

    asyncio.run(scenario())
