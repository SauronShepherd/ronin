from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import pytest
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
from studio_storage import SqliteJobStore
from studio_worker import (
    LocalWorkerRuntime,
    LocalWorkerRuntimeConfig,
    WorkerPaths,
    runtime_catalog_for_image,
)

START = Instant("2026-09-06T18:30:00.000000Z")
AFTER_EXPIRY = Instant("2026-09-06T18:30:31.000000Z")
IMAGE = "sha256:" + "1" * 64


def _job() -> Job:
    return Job(
        id=JobId("job-runtime"),
        project_id="examples/demo",
        idempotency_key="runtime-key",
        request_digest="a" * 64,
        state=JobState.QUEUED,
        created_at=START,
        updated_at=START,
        target="notebooks/etl.ronin.json",
        parameters_json='{"mode":"test"}',
    )


def _run() -> Run:
    return Run(
        id=RunId("run-runtime"),
        job_id=JobId("job-runtime"),
        ordinal=1,
        state=RunState.PENDING,
        not_before=START,
        created_at=START,
        updated_at=START,
    )


def _config(tmp_path: Path) -> LocalWorkerRuntimeConfig:
    return LocalWorkerRuntimeConfig(
        paths=WorkerPaths(Path.cwd(), tmp_path),
        owner="worker-runtime",
        image=IMAGE,
        heartbeat_interval_seconds=10.0,
    )


@dataclass
class _Clock:
    value: Instant

    def __call__(self) -> Instant:
        return self.value


@dataclass
class _Runner:
    block_on_call: int | None = None
    started: asyncio.Event = field(default_factory=asyncio.Event)
    calls: int = 0
    cancellation_args: list[tuple[str, ...]] = field(default_factory=list)

    async def run(
        self,
        args: tuple[str, ...],
        *,
        input_text: str,
        cancellation: CancellationSignal,
        timeout_seconds: float,
        cancellation_args: tuple[str, ...],
    ) -> CommandOutcome:
        del args, input_text, timeout_seconds
        self.calls += 1
        self.cancellation_args.append(cancellation_args)
        if self.block_on_call == self.calls:
            self.started.set()
            await asyncio.Event().wait()
        assert not cancellation.is_cancelled
        return CommandOutcome(0, f"cell-{self.calls}", False, False, 1)


def _seed(config: LocalWorkerRuntimeConfig) -> None:
    store = SqliteJobStore(config.database_path, migration_now=START)
    store.create_job(_job(), _run())


def test_runtime_config_and_catalog_fail_closed(tmp_path: Path) -> None:
    paths = WorkerPaths(Path.cwd(), tmp_path)
    with pytest.raises(ValueError, match="database name"):
        LocalWorkerRuntimeConfig(paths, "worker", IMAGE, database_name="../ronin.sqlite3")
    with pytest.raises(ValueError, match="immutable sha256"):
        LocalWorkerRuntimeConfig(paths, "worker", "python:3.11-slim")

    catalog = runtime_catalog_for_image(IMAGE)
    profile = catalog.profiles[0]
    assert profile.ref.adapter_id == "docker"
    assert profile.capability("execution-image") is not None
    assert profile.capability("execution-image").value == IMAGE


@pytest.mark.asyncio
async def test_run_once_executes_claim_through_sqlite_and_container_boundary(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _seed(config)
    runner = _Runner()

    async with LocalWorkerRuntime(
        config,
        migration_now=START,
        command_runner=runner,
        engine_path="docker",
        now=_Clock(START),
    ) as runtime:
        outcome = await runtime.run_once(
            attempt_id=AttemptId("attempt-runtime-1"),
            lease_token=LeaseToken("lease-runtime-1"),
        )

    assert outcome.attempt_id == AttemptId("attempt-runtime-1")
    assert outcome.execution is not None
    assert outcome.execution.state.value == "succeeded"
    assert len(outcome.execution.executed_cell_ids) == 5
    assert outcome.execution.reused_cell_ids == ()
    assert runner.calls == 5
    assert all(args[:3] == ("docker", "rm", "-f") for args in runner.cancellation_args)

    store = SqliteJobStore(config.database_path, migration_now=START)
    assert store.get_job(JobId("job-runtime")).state is JobState.SUCCEEDED
    assert len(store.read_cell_results(RunId("run-runtime"))) == 5


@pytest.mark.asyncio
async def test_restart_reclaims_same_run_and_reuses_persisted_cells(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _seed(config)
    first_runner = _Runner(block_on_call=4)

    runtime1 = LocalWorkerRuntime(
        config,
        migration_now=START,
        command_runner=first_runner,
        engine_path="docker",
        now=_Clock(START),
    )
    first_task = asyncio.create_task(
        runtime1.run_once(
            attempt_id=AttemptId("attempt-runtime-1"),
            lease_token=LeaseToken("lease-runtime-1"),
        )
    )
    await asyncio.wait_for(first_runner.started.wait(), timeout=2.0)

    store = SqliteJobStore(config.database_path, migration_now=START)
    persisted_before_crash = store.read_cell_results(RunId("run-runtime"))
    assert len(persisted_before_crash) == 3

    first_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_task
    await runtime1.aclose()

    second_runner = _Runner()
    async with LocalWorkerRuntime(
        config,
        migration_now=AFTER_EXPIRY,
        command_runner=second_runner,
        engine_path="docker",
        now=_Clock(AFTER_EXPIRY),
    ) as runtime2:
        outcome = await runtime2.run_once(
            attempt_id=AttemptId("attempt-runtime-2"),
            lease_token=LeaseToken("lease-runtime-2"),
        )

    assert outcome.reclaimed_run_ids == (RunId("run-runtime"),)
    assert outcome.attempt_id == AttemptId("attempt-runtime-2")
    assert outcome.execution is not None
    assert len(outcome.execution.reused_cell_ids) == 3
    assert len(outcome.execution.executed_cell_ids) == 2
    assert second_runner.calls == 2

    final_store = SqliteJobStore(config.database_path, migration_now=AFTER_EXPIRY)
    assert final_store.get_job(JobId("job-runtime")).state is JobState.SUCCEEDED
    assert len(final_store.read_cell_results(RunId("run-runtime"))) == 5
