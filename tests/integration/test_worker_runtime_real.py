from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
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
from studio_runners import ContainerExecutionLimits
from studio_storage import SqliteJobStore
from studio_worker import LocalWorkerRuntime, LocalWorkerRuntimeConfig, WorkerPaths

if os.environ.get("RONIN_REAL_DOCKER_QUALIFICATION") != "1":
    pytest.skip(
        "real Docker qualification runs only in the dedicated CI job",
        allow_module_level=True,
    )

_IMAGE = os.environ["RONIN_DOCKER_QUALIFICATION_IMAGE"]
_DOCKER = shutil.which("docker")
if _DOCKER is None:
    raise RuntimeError("dedicated Docker qualification requires the docker client")

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


def _seed(
    config: LocalWorkerRuntimeConfig,
    *,
    job_id: str = "job-real-demo",
    run_id: str = "run-real-demo",
    key: str = "real-demo-key",
) -> None:
    store = SqliteJobStore(config.database_path, migration_now=_NOW)
    store.create_job(
        Job(
            id=JobId(job_id),
            project_id="examples/demo",
            idempotency_key=key,
            request_digest="b" * 64,
            state=JobState.QUEUED,
            created_at=_NOW,
            updated_at=_NOW,
            target="notebooks/etl.ronin.json",
            parameters_json='{"mode":"qualification"}',
        ),
        Run(
            id=RunId(run_id),
            job_id=JobId(job_id),
            ordinal=1,
            state=RunState.PENDING,
            not_before=_NOW,
            created_at=_NOW,
            updated_at=_NOW,
        ),
    )


def _log_outputs(root: Path) -> tuple[str, ...]:
    outputs: list[str] = []
    for path in sorted(root.glob("*/*/log.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        outputs.append(str(payload["output"]).strip())
    return tuple(outputs)


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


def test_real_docker_worker_executes_clean_container_demo(tmp_path: Path) -> None:
    async def scenario() -> None:
        config = LocalWorkerRuntimeConfig(
            paths=WorkerPaths(Path.cwd(), tmp_path),
            owner="worker-real-demo",
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

        async with LocalWorkerRuntime(
            config,
            migration_now=_NOW,
            engine_path=_DOCKER,
            now=lambda: _NOW,
        ) as runtime:
            outcome = await runtime.run_once(
                attempt_id=AttemptId("attempt-real-demo-1"),
                lease_token=LeaseToken("lease-real-demo-1"),
            )

        assert outcome.execution is not None
        assert outcome.execution.state.value == "succeeded"
        assert len(outcome.execution.executed_cell_ids) == 6
        assert outcome.execution.reused_cell_ids == ()

        store = SqliteJobStore(config.database_path, migration_now=_NOW)
        job = store.get_job(JobId("job-real-demo"))
        assert job is not None
        assert job.state is JobState.SUCCEEDED
        assert len(store.read_cell_results(RunId("run-real-demo"))) == 6

        outputs = _log_outputs(config.execution_evidence_root)
        assert len(outputs) == 6
        assert any("Ronin v0.1 demo" in output for output in outputs)
        assert any("extracted 100 customers" in output for output in outputs)
        assert any("extracted 500 orders" in output for output in outputs)
        assert any("quality checks passed" in output for output in outputs)
        publish = next(output for output in outputs if '"dataset": "revenue_by_region"' in output)
        published = json.loads(publish)
        assert published["rows"] == 2
        assert published["totals"] == {"eu": 187500, "us": 186750}

    asyncio.run(scenario())


def test_real_process_sigkill_reclaims_same_run_and_reuses_three_cells(tmp_path: Path) -> None:
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
    _seed(
        config,
        job_id="job-process-crash",
        run_id="run-process-crash",
        key="process-crash-key",
    )

    # Every argument is constructed locally from the checked-out repository, temporary paths,
    # and the Docker executable resolved by the dedicated qualification job.
    first = subprocess.Popen(  # noqa: S603
        _process_args("crash", config, marker, outcome_path),
        cwd=Path.cwd(),
        text=True,
    )
    try:
        _wait_for_path(marker, first, timeout=20.0)
        store = SqliteJobStore(config.database_path, migration_now=_NOW)
        before_crash = store.read_cell_results(RunId("run-process-crash"))
        assert len(before_crash) == 3

        first.kill()
        assert first.wait(timeout=5.0) != 0

        # The v0.1 lease contract is 30 seconds. Do not shortcut reclaim in qualification.
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
        assert outcome["reclaimed"] == ["run-process-crash"]
        assert outcome["attempt_id"] == "attempt-process-replacement"
        assert outcome["state"] == "succeeded"
        assert len(outcome["reused"]) == 3
        assert len(outcome["executed"]) == 3
        assert set(outcome["reused"]) == {result.cell_id for result in before_crash}

        final_store = SqliteJobStore(config.database_path, migration_now=_NOW)
        job = final_store.get_job(JobId("job-process-crash"))
        assert job is not None
        assert job.state is JobState.SUCCEEDED
        assert len(final_store.read_cell_results(RunId("run-process-crash"))) == 6
        events = final_store.read_events(RunId("run-process-crash"), since=0)
        assert sum(event.kind == "worker.attempt.succeeded" for event in events) == 1
    finally:
        if first.poll() is None:
            first.kill()
            first.wait(timeout=5.0)
