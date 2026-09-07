"""Ronin v0.1 acceptance journey.

Every step maps 1:1 to docs/product/V01_SCOPE.md section 4. Tests unskip as their
capability lands. All fifteen must pass before v0.1 is tagged.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest
from studio_orchestrator import Instant, Job, JobId, JobState, Run, RunId, RunState
from studio_runners import ContainerExecutionLimits
from studio_storage import SqliteJobStore
from studio_worker import LocalWorkerRuntimeConfig, WorkerPaths

pytestmark = pytest.mark.e2e

_IMAGE = os.environ.get("RONIN_DOCKER_QUALIFICATION_IMAGE")
_DOCKER = shutil.which("docker")
_RONIN = shutil.which("ronin")
_NOW = Instant("2026-09-06T20:00:00.000000Z")
_PROCESS_PROBE = r"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from studio_kernel import CancellationSignal
from studio_orchestrator import AttemptId, Instant, LeaseToken
from studio_runners import AsyncioCommandRunner, CommandOutcome, ContainerExecutionLimits
from studio_worker import LocalWorkerRuntime, LocalWorkerRuntimeConfig, WorkerPaths


class GateBeforeFourthDockerRun:
    def __init__(self, marker: Path) -> None:
        self._inner = AsyncioCommandRunner()
        self._marker = marker
        self._calls = 0

    async def run(
        self,
        args: tuple[str, ...],
        *,
        input_text: str,
        cancellation: CancellationSignal,
        timeout_seconds: float,
        cancellation_args: tuple[str, ...],
    ) -> CommandOutcome:
        self._calls += 1
        if self._calls == 4:
            self._marker.write_text("three-checkpoints-persisted\n", encoding="utf-8")
            await asyncio.Event().wait()
        return await self._inner.run(
            args,
            input_text=input_text,
            cancellation=cancellation,
            timeout_seconds=timeout_seconds,
            cancellation_args=cancellation_args,
        )


async def main() -> None:
    mode, workspace, data_dir, image, docker, marker, outcome_path = sys.argv[1:]
    config = LocalWorkerRuntimeConfig(
        paths=WorkerPaths(Path(workspace), Path(data_dir)),
        owner=f"worker-process-{mode}",
        image=image,
        limits=ContainerExecutionLimits(
            cpus="0.5",
            memory="128m",
            pids=32,
            timeout_seconds=10.0,
        ),
        heartbeat_interval_seconds=10.0,
    )
    runner = GateBeforeFourthDockerRun(Path(marker)) if mode == "crash" else None
    async with LocalWorkerRuntime(
        config,
        migration_now=Instant("2026-09-06T20:00:00.000000Z"),
        command_runner=runner,
        engine_path=docker,
    ) as runtime:
        result = await runtime.run_once(
            attempt_id=AttemptId(f"attempt-process-{mode}"),
            lease_token=LeaseToken(f"lease-process-{mode}"),
        )
    if mode == "replacement":
        assert result.execution is not None
        Path(outcome_path).write_text(
            json.dumps(
                {
                    "reclaimed": [str(run_id) for run_id in result.reclaimed_run_ids],
                    "attempt_id": str(result.attempt_id),
                    "state": result.execution.state.value,
                    "executed": list(result.execution.executed_cell_ids),
                    "reused": list(result.execution.reused_cell_ids),
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )


asyncio.run(main())
"""


def _docker_qualification_ready() -> bool:
    return (
        os.environ.get("RONIN_REAL_DOCKER_QUALIFICATION") == "1"
        and _IMAGE is not None
        and _DOCKER is not None
    )


def _ronin(*args: str) -> subprocess.CompletedProcess[str]:
    assert _RONIN is not None, "installed ronin console entry point is required"
    return subprocess.run(  # noqa: S603
        (_RONIN, *args),
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
        timeout=15.0,
    )


def _seed(config: LocalWorkerRuntimeConfig) -> None:
    store = SqliteJobStore(config.database_path, migration_now=_NOW)
    store.create_job(
        Job(
            id=JobId("job-v01-acceptance"),
            project_id="examples/demo",
            idempotency_key="v01-acceptance-key",
            request_digest="b" * 64,
            state=JobState.QUEUED,
            created_at=_NOW,
            updated_at=_NOW,
            target="notebooks/etl.ronin.json",
            parameters_json='{"mode":"qualification"}',
        ),
        Run(
            id=RunId("run-v01-acceptance"),
            job_id=JobId("job-v01-acceptance"),
            ordinal=1,
            state=RunState.PENDING,
            not_before=_NOW,
            created_at=_NOW,
            updated_at=_NOW,
        ),
    )


def _wait_for_path(path: Path, process: subprocess.Popen[str], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process.poll() is not None:
            raise AssertionError(f"worker process exited early with {process.returncode}")
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for worker marker: {path}")


def _process_args(
    mode: str,
    config: LocalWorkerRuntimeConfig,
    marker: Path,
    outcome: Path,
) -> list[str]:
    assert _IMAGE is not None
    assert _DOCKER is not None
    return [
        sys.executable,
        "-c",
        _PROCESS_PROBE,
        mode,
        str(Path.cwd()),
        str(config.paths.data_dir),
        _IMAGE,
        _DOCKER,
        str(marker),
        str(outcome),
    ]


def _attempt_rows(database_path: Path) -> list[sqlite3.Row]:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        return list(
            connection.execute(
                "SELECT attempt_id, state, lease_expires_at FROM attempts ORDER BY ordinal"
            ).fetchall()
        )


@pytest.fixture(scope="module")
def worker_restart_journey(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    if not _docker_qualification_ready():
        pytest.skip("live worker acceptance requires the dedicated real-Docker qualification job")

    tmp_path = tmp_path_factory.mktemp("v01-worker-restart")
    data_dir = tmp_path / "process-crash"
    marker = tmp_path / "three-persisted.marker"
    outcome_path = tmp_path / "replacement-outcome.json"
    config = LocalWorkerRuntimeConfig(
        paths=WorkerPaths(Path.cwd(), data_dir),
        owner="parent-seed-only",
        image=_IMAGE,
        limits=ContainerExecutionLimits(
            cpus="0.5",
            memory="128m",
            pids=32,
            timeout_seconds=10.0,
        ),
        heartbeat_interval_seconds=10.0,
    )
    _seed(config)

    first = subprocess.Popen(  # noqa: S603
        _process_args("crash", config, marker, outcome_path),
        cwd=Path.cwd(),
        text=True,
    )
    try:
        _wait_for_path(marker, first, timeout=20.0)
        store = SqliteJobStore(config.database_path, migration_now=_NOW)
        before_crash = store.read_cell_results(RunId("run-v01-acceptance"))
        assert len(before_crash) == 3

        first.kill()
        assert first.wait(timeout=5.0) != 0
        orphaned_attempts = _attempt_rows(config.database_path)
        assert len(orphaned_attempts) == 1
        assert orphaned_attempts[0]["state"] == "running"
        assert orphaned_attempts[0]["lease_expires_at"] is not None

        # Production acceptance deliberately keeps the real 30-second lease contract.
        time.sleep(31.0)

        second = subprocess.run(  # noqa: S603
            _process_args("replacement", config, marker, outcome_path),
            cwd=Path.cwd(),
            text=True,
            check=False,
            timeout=30.0,
        )
        assert second.returncode == 0
        outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
        final_store = SqliteJobStore(config.database_path, migration_now=_NOW)
        final_results = final_store.read_cell_results(RunId("run-v01-acceptance"))
        events = final_store.read_events(RunId("run-v01-acceptance"), since=0)
        job = final_store.get_job(JobId("job-v01-acceptance"))
        return {
            "before_crash": before_crash,
            "orphaned_attempts": orphaned_attempts,
            "outcome": outcome,
            "final_results": final_results,
            "events": events,
            "job": job,
        }
    finally:
        if first.poll() is None:
            first.kill()
            first.wait(timeout=5.0)


@pytest.mark.skip(reason="W6: compose file does not exist yet")
def test_step_01_compose_reaches_healthy_within_60s() -> None: ...


def test_step_02_doctor_reports_all_checks_passing() -> None:
    result = _ronin("doctor", "--require=core")
    assert result.returncode == 0, result.stderr
    assert "python>=3.11: ok" in result.stdout
    assert "git: ok" in result.stdout
    assert "docker:" in result.stdout
    assert "doctor: required core checks passed" in result.stdout


def test_step_03_validate_accepts_demo_project() -> None:
    result = _ronin("validate", "examples/demo")
    assert result.returncode == 0, result.stderr
    assert "validate: ok" in result.stdout
    assert "notebooks: 1" in result.stdout


def test_step_04_plan_prints_order_and_levels() -> None:
    result = _ronin("plan", "examples/demo", "-t", "notebooks/etl")
    assert result.returncode == 0, result.stderr
    assert "execution order:" in result.stdout
    assert "1. extract-customers" in result.stdout
    assert "2. extract-orders" in result.stdout
    assert "3. join-and-aggregate" in result.stdout
    assert "4. quality-check" in result.stdout
    assert "5. publish" in result.stdout
    assert "0: extract-customers, extract-orders" in result.stdout
    assert "1: join-and-aggregate" in result.stdout
    assert "2: quality-check" in result.stdout
    assert "3: publish" in result.stdout


@pytest.mark.skip(reason="W4: POST /v1/jobs does not exist yet")
def test_step_05_submit_returns_queued_job() -> None: ...


def test_step_06_worker_claims_and_executes_first_cells(
    worker_restart_journey: dict[str, object],
) -> None:
    before_crash = worker_restart_journey["before_crash"]
    assert len(before_crash) == 3


def test_step_07_kill_worker_orphans_lease(worker_restart_journey: dict[str, object]) -> None:
    orphaned_attempts = worker_restart_journey["orphaned_attempts"]
    assert len(orphaned_attempts) == 1
    assert orphaned_attempts[0]["state"] == "running"
    assert orphaned_attempts[0]["lease_expires_at"] is not None


def test_step_08_restart_waits_for_lease_expiry(worker_restart_journey: dict[str, object]) -> None:
    outcome = worker_restart_journey["outcome"]
    assert outcome["attempt_id"] == "attempt-process-replacement"
    assert outcome["reclaimed"] == ["run-v01-acceptance"]


def test_step_09_reclaimed_attempt_resumes_at_cell_four(
    worker_restart_journey: dict[str, object],
) -> None:
    before_crash = worker_restart_journey["before_crash"]
    outcome = worker_restart_journey["outcome"]
    final_results = worker_restart_journey["final_results"]
    events = worker_restart_journey["events"]
    job = worker_restart_journey["job"]

    assert outcome["state"] == "succeeded"
    assert len(outcome["reused"]) == 3
    assert len(outcome["executed"]) == 2
    assert set(outcome["reused"]) == {result.cell_id for result in before_crash}
    assert len(final_results) == 5
    assert job is not None
    assert job.state is JobState.SUCCEEDED
    assert sum(event.kind == "worker.attempt.succeeded" for event in events) == 1


@pytest.mark.skip(reason="W4: GET /v1/jobs/{id} does not exist yet")
def test_step_10_job_reaches_succeeded() -> None: ...


@pytest.mark.skip(reason="W4: events endpoint does not exist yet")
def test_step_11_events_contiguous_across_attempts_with_terminal() -> None: ...


@pytest.mark.skip(reason="W4: evidence endpoint does not exist yet")
def test_step_12_evidence_present_for_all_six_cells() -> None: ...


@pytest.mark.skip(reason="W4: idempotency does not exist yet")
def test_step_13_replayed_idempotency_key_returns_same_job() -> None: ...


@pytest.mark.skip(reason="W4: cancel does not exist yet")
def test_step_14_cancel_removes_container() -> None: ...


@pytest.mark.skip(reason="W4: SDK contract alignment not done yet")
def test_step_15_sdk_round_trip_matches_cli() -> None: ...


def test_journey_progress_is_reported(record_property) -> None:
    """Emit how many acceptance steps are live without gating on that count."""
    steps = [value for name, value in globals().items() if name.startswith("test_step_")]
    skipped = sum(
        1 for step in steps if any(mark.name == "skip" for mark in getattr(step, "pytestmark", []))
    )
    record_property("acceptance_steps_live", len(steps) - skipped)
    record_property("acceptance_steps_total", len(steps))
    assert len(steps) == 15
