"""Ronin v0.1 acceptance journey.

Every step maps 1:1 to docs/product/V01_SCOPE.md section 4. Tests unskip as their
capability lands. All fifteen must pass before v0.1 is tagged.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from threading import Thread

import pytest
from pyronin import HTTPTransport, Ronin
from studio_cli import main as cli_main
from studio_execution import DurableExecutionService
from studio_orchestrator import (
    AttemptId,
    AttemptState,
    Instant,
    Job,
    JobId,
    JobState,
    LeaseToken,
    Run,
    RunId,
    RunState,
    StoredExecutionEvent,
)
from studio_runners import ContainerExecutionLimits
from studio_server import RoninHTTPServer
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
from contextlib import suppress
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


class LongFirstDockerRun:
    def __init__(self, marker: Path) -> None:
        self._inner = AsyncioCommandRunner()
        self._marker = marker
        self._calls = 0

    async def _mark_running(self, docker: str, name: str) -> None:
        while True:
            probe = await asyncio.create_subprocess_exec(
                docker,
                "ps",
                "--filter",
                f"name=^{name}$",
                "--format",
                "{{.Names}}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await probe.communicate()
            if probe.returncode == 0 and name in stdout.decode().splitlines():
                self._marker.write_text(name + "\n", encoding="utf-8")
                return
            await asyncio.sleep(0.05)

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
        if self._calls != 1:
            return await self._inner.run(
                args,
                input_text=input_text,
                cancellation=cancellation,
                timeout_seconds=timeout_seconds,
                cancellation_args=cancellation_args,
            )
        name = cancellation_args[-1]
        monitor = asyncio.create_task(self._mark_running(cancellation_args[0], name))
        try:
            return await self._inner.run(
                args,
                input_text="import time\ntime.sleep(120)\n",
                cancellation=cancellation,
                timeout_seconds=timeout_seconds,
                cancellation_args=cancellation_args,
            )
        finally:
            monitor.cancel()
            with suppress(asyncio.CancelledError):
                await monitor


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
            timeout_seconds=300.0 if mode == "cancel" else 10.0,
        ),
        heartbeat_interval_seconds=10.0,
    )
    if mode == "crash":
        runner = GateBeforeFourthDockerRun(Path(marker))
    elif mode == "cancel":
        runner = LongFirstDockerRun(Path(marker))
    else:
        runner = None
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
    if mode in {"replacement", "cancel"}:
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


def _cli_json(*args: str) -> object:
    output = StringIO()
    with redirect_stdout(output):
        assert cli_main(list(args)) == 0
    text = output.getvalue().strip()
    return json.loads(text)


def _cli_json_lines(*args: str) -> list[object]:
    output = StringIO()
    with redirect_stdout(output):
        assert cli_main(list(args)) == 0
    return [json.loads(line) for line in output.getvalue().splitlines() if line]


def _seed(
    config: LocalWorkerRuntimeConfig,
    *,
    job_id: str = "job-v01-acceptance",
    run_id: str = "run-v01-acceptance",
    key: str = "v01-acceptance-key",
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
def operator_journey(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    tmp_path = tmp_path_factory.mktemp("v01-operator")
    store = SqliteJobStore(tmp_path / "ronin.db", migration_now=_NOW)
    service = DurableExecutionService(store, max_workers=2, max_in_flight=4)
    auth_value = "v01-operator-auth"
    server = RoninHTTPServer(("127.0.0.1", 0), service, token=auth_value)
    thread = Thread(target=server.serve_forever, name="v01-operator-http", daemon=True)
    thread.start()
    old_url = os.environ.get("RONIN_URL")
    old_auth_value = os.environ.get("RONIN_TOKEN")
    os.environ["RONIN_URL"] = f"http://127.0.0.1:{server.server_port}"
    os.environ["RONIN_TOKEN"] = auth_value
    try:
        submitted = _cli_json(
            "submit",
            "examples/demo",
            "-t",
            "notebooks/etl.ronin.json",
            "--idempotency-key",
            "v01-cli-k1",
            "--param",
            "limit=7",
            "--json",
        )
        assert isinstance(submitted, dict)
        job_id = str(submitted["id"])
        run_id = store.get_run_id_for_job(JobId(job_id))
        assert run_id is not None

        first_attempt = AttemptId("attempt-v01-cli-1")
        first_lease = LeaseToken("lease-v01-cli-1")
        claimed = store.claim_next_run(
            owner="worker-v01-cli-1",
            lease_token=first_lease,
            attempt_id=first_attempt,
            lease_seconds=1,
            now=Instant("2099-01-01T00:00:00.000000Z"),
        )
        assert claimed is not None
        store.append_events(
            first_attempt,
            (
                StoredExecutionEvent(first_attempt, 0, "cell.succeeded", "cell-1", Instant("2099-01-01T00:00:00.100000Z")),
                StoredExecutionEvent(first_attempt, 1, "cell.succeeded", "cell-2", Instant("2099-01-01T00:00:00.200000Z")),
            ),
            owner="worker-v01-cli-1",
            lease_token=first_lease,
            now=Instant("2099-01-01T00:00:00.500000Z"),
        )
        assert store.reclaim_expired(now=Instant("2099-01-01T00:00:02.000000Z")) == (run_id,)

        second_attempt = AttemptId("attempt-v01-cli-2")
        second_lease = LeaseToken("lease-v01-cli-2")
        claimed = store.claim_next_run(
            owner="worker-v01-cli-2",
            lease_token=second_lease,
            attempt_id=second_attempt,
            lease_seconds=30,
            now=Instant("2099-01-01T00:00:03.000000Z"),
        )
        assert claimed is not None
        store.append_events(
            second_attempt,
            (
                StoredExecutionEvent(second_attempt, 0, "cell.succeeded", "cell-3", Instant("2099-01-01T00:00:03.100000Z")),
                StoredExecutionEvent(second_attempt, 1, "worker.attempt.succeeded", "terminal", Instant("2099-01-01T00:00:03.200000Z")),
            ),
            owner="worker-v01-cli-2",
            lease_token=second_lease,
            now=Instant("2099-01-01T00:00:03.500000Z"),
        )
        store.complete_attempt(
            second_attempt,
            state=AttemptState.SUCCEEDED,
            failure_code=None,
            owner="worker-v01-cli-2",
            lease_token=second_lease,
            now=Instant("2099-01-01T00:00:04.000000Z"),
        )

        status = _cli_json("status", job_id, "--json")
        logs = _cli_json_lines("logs", job_id, "--json")
        replay = _cli_json(
            "submit",
            "examples/demo",
            "-t",
            "notebooks/etl.ronin.json",
            "--idempotency-key",
            "v01-cli-k1",
            "--param",
            "limit=7",
            "--json",
        )
        transport = HTTPTransport(
            f"http://127.0.0.1:{server.server_port}",
            token=auth_value,
            allow_insecure_localhost=True,
            max_retries=0,
        )
        sdk = Ronin(transport=transport)
        sdk_result = sdk.submit(
            project="examples/demo",
            target="notebooks/etl.ronin.json",
            parameters={"limit": 7},
            idempotency_key="v01-cli-k1",
        ).wait(poll_interval=0.01, timeout=1.0)
        page = store.list_jobs(project_id="examples/demo", state=None, limit=10, cursor=None)
        yield {
            "submitted": submitted,
            "job_id": job_id,
            "run_id": run_id,
            "status": status,
            "logs": logs,
            "replay": replay,
            "sdk_result": sdk_result,
            "job_count": len(page.items),
            "run_id_after": store.get_run_id_for_job(JobId(job_id)),
            "first_attempt": first_attempt,
            "second_attempt": second_attempt,
        }
    finally:
        if old_url is None:
            os.environ.pop("RONIN_URL", None)
        else:
            os.environ["RONIN_URL"] = old_url
        if old_auth_value is None:
            os.environ.pop("RONIN_TOKEN", None)
        else:
            os.environ["RONIN_TOKEN"] = old_auth_value
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)
        assert not thread.is_alive()


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
        limits=ContainerExecutionLimits(cpus="0.5", memory="128m", pids=32, timeout_seconds=10.0),
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
            "database_path": config.database_path,
        }
    finally:
        if first.poll() is None:
            first.kill()
            first.wait(timeout=5.0)


@pytest.fixture(scope="module")
def worker_cancel_journey(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    if not _docker_qualification_ready():
        pytest.skip("live cancellation acceptance requires the dedicated real-Docker qualification job")

    tmp_path = tmp_path_factory.mktemp("v01-worker-cancel")
    marker = tmp_path / "container-running.marker"
    outcome_path = tmp_path / "cancel-outcome.json"
    config = LocalWorkerRuntimeConfig(
        paths=WorkerPaths(Path.cwd(), tmp_path / "cancel-data"),
        owner="parent-cancel-server",
        image=_IMAGE,
        limits=ContainerExecutionLimits(cpus="0.5", memory="128m", pids=32, timeout_seconds=300.0),
        heartbeat_interval_seconds=10.0,
    )
    _seed(config, job_id="job-v01-cancel", run_id="run-v01-cancel", key="v01-cancel-key")

    store = SqliteJobStore(config.database_path, migration_now=_NOW)
    service = DurableExecutionService(store, max_workers=2, max_in_flight=4)
    auth_value = "v01-cancel-auth"
    server = RoninHTTPServer(("127.0.0.1", 0), service, token=auth_value)
    thread = Thread(target=server.serve_forever, name="v01-cancel-http", daemon=True)
    thread.start()
    old_url = os.environ.get("RONIN_URL")
    old_auth_value = os.environ.get("RONIN_TOKEN")
    os.environ["RONIN_URL"] = f"http://127.0.0.1:{server.server_port}"
    os.environ["RONIN_TOKEN"] = auth_value
    process = subprocess.Popen(  # noqa: S603
        _process_args("cancel", config, marker, outcome_path), cwd=Path.cwd(), text=True
    )
    try:
        _wait_for_path(marker, process, timeout=20.0)
        container_name = marker.read_text(encoding="utf-8").strip()
        assert container_name.startswith("ronin-")
        started = time.monotonic()
        cancelled = _cli_json("cancel", "job-v01-cancel", "--json")
        assert isinstance(cancelled, dict)
        assert cancelled["state"] == "cancelling"
        assert process.wait(timeout=10.0) == 0
        elapsed = time.monotonic() - started
        outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
        final_store = SqliteJobStore(config.database_path, migration_now=_NOW)
        job = final_store.get_job(JobId("job-v01-cancel"))
        docker_ps = subprocess.run(  # noqa: S603
            (_DOCKER, "ps", "--filter", f"name=^{container_name}$", "--format", "{{.Names}}"),
            text=True,
            capture_output=True,
            check=False,
            timeout=5.0,
        )
        return {
            "outcome": outcome,
            "job": job,
            "container_name": container_name,
            "docker_ps": docker_ps,
            "elapsed": elapsed,
        }
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5.0)
        if old_url is None:
            os.environ.pop("RONIN_URL", None)
        else:
            os.environ["RONIN_URL"] = old_url
        if old_auth_value is None:
            os.environ.pop("RONIN_TOKEN", None)
        else:
            os.environ["RONIN_TOKEN"] = old_auth_value
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)
        assert not thread.is_alive()
        asyncio.run(service.aclose())


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
    assert "1. intro" in result.stdout
    assert "2. extract-customers" in result.stdout
    assert "3. extract-orders" in result.stdout
    assert "4. join-and-aggregate" in result.stdout
    assert "5. quality-check" in result.stdout
    assert "6. publish" in result.stdout
    assert "0: intro, extract-customers, extract-orders" in result.stdout
    assert "1: join-and-aggregate" in result.stdout
    assert "2: quality-check" in result.stdout
    assert "3: publish" in result.stdout


def test_step_05_submit_returns_queued_job(operator_journey: dict[str, object]) -> None:
    submitted = operator_journey["submitted"]
    assert submitted["id"] == operator_journey["job_id"]
    assert submitted["state"] == "queued"


def test_step_06_worker_claims_and_executes_first_cells(worker_restart_journey: dict[str, object]) -> None:
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


def test_step_09_reclaimed_attempt_resumes_at_cell_four(worker_restart_journey: dict[str, object]) -> None:
    before_crash = worker_restart_journey["before_crash"]
    outcome = worker_restart_journey["outcome"]
    final_results = worker_restart_journey["final_results"]
    events = worker_restart_journey["events"]
    job = worker_restart_journey["job"]

    assert outcome["state"] == "succeeded"
    assert len(outcome["reused"]) == 3
    assert len(outcome["executed"]) == 3
    assert set(outcome["reused"]) == {result.cell_id for result in before_crash}
    assert len(final_results) == 6
    assert job is not None
    assert job.state is JobState.SUCCEEDED
    assert sum(event.kind == "worker.attempt.succeeded" for event in events) == 1


def test_step_10_job_reaches_succeeded(operator_journey: dict[str, object]) -> None:
    status = operator_journey["status"]
    assert status["id"] == operator_journey["job_id"]
    assert status["state"] == "succeeded"


def test_step_11_events_contiguous_across_attempts_with_terminal(operator_journey: dict[str, object]) -> None:
    logs = operator_journey["logs"]
    assert [event["sequence"] for event in logs] == [0, 1, 2, 3]
    assert [event["attempt_id"] for event in logs] == [
        str(operator_journey["first_attempt"]),
        str(operator_journey["first_attempt"]),
        str(operator_journey["second_attempt"]),
        str(operator_journey["second_attempt"]),
    ]
    assert logs[-1]["kind"] == "worker.attempt.succeeded"


def test_step_12_evidence_present_for_all_six_cells(worker_restart_journey: dict[str, object]) -> None:
    database_path = worker_restart_journey["database_path"]
    assert isinstance(database_path, Path)
    store = SqliteJobStore(database_path, migration_now=_NOW)
    service = DurableExecutionService(store, max_workers=2, max_in_flight=4)
    auth_value = "v01-evidence-auth"
    server = RoninHTTPServer(("127.0.0.1", 0), service, token=auth_value)
    thread = Thread(target=server.serve_forever, name="v01-evidence-http", daemon=True)
    thread.start()
    old_url = os.environ.get("RONIN_URL")
    old_auth_value = os.environ.get("RONIN_TOKEN")
    os.environ["RONIN_URL"] = f"http://127.0.0.1:{server.server_port}"
    os.environ["RONIN_TOKEN"] = auth_value
    try:
        items = _cli_json_lines("evidence", "job-v01-acceptance", "--json")
        assert len(items) == 12
        by_cell: dict[str, set[str]] = {}
        for item in items:
            assert isinstance(item, dict)
            assert item["availability"] == "available"
            assert item["digest_algorithm"] == "sha256"
            assert isinstance(item["digest"], str) and len(item["digest"]) == 64
            assert isinstance(item["size_bytes"], int) and item["size_bytes"] >= 0
            assert "storage_ref" not in item
            assert "locator" not in item
            cell_id = item["cell_id"]
            role = item["role"]
            assert isinstance(cell_id, str)
            assert isinstance(role, str)
            by_cell.setdefault(cell_id, set()).add(role)
        assert len(by_cell) == 6
        assert all(roles == {"log", "resource"} for roles in by_cell.values())

        sdk = Ronin(
            transport=HTTPTransport(
                f"http://127.0.0.1:{server.server_port}",
                token=auth_value,
                allow_insecure_localhost=True,
                max_retries=0,
            )
        )
        sdk_items = sdk.get_evidence("job-v01-acceptance")
        assert len(sdk_items) == 12
        assert all(item.portable_identity is not None for item in sdk_items)
    finally:
        if old_url is None:
            os.environ.pop("RONIN_URL", None)
        else:
            os.environ["RONIN_URL"] = old_url
        if old_auth_value is None:
            os.environ.pop("RONIN_TOKEN", None)
        else:
            os.environ["RONIN_TOKEN"] = old_auth_value
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)
        assert not thread.is_alive()


def test_step_13_replayed_idempotency_key_returns_same_job(operator_journey: dict[str, object]) -> None:
    replay = operator_journey["replay"]
    assert replay["id"] == operator_journey["job_id"]
    assert replay["state"] == "succeeded"
    assert operator_journey["run_id_after"] == operator_journey["run_id"]
    assert operator_journey["job_count"] == 1


def test_step_14_cancel_removes_container(worker_cancel_journey: dict[str, object]) -> None:
    outcome = worker_cancel_journey["outcome"]
    job = worker_cancel_journey["job"]
    docker_ps = worker_cancel_journey["docker_ps"]
    assert outcome["state"] == "cancelled"
    assert job is not None
    assert job.state is JobState.CANCELLED
    assert docker_ps.returncode == 0
    assert docker_ps.stdout.strip() == ""
    assert worker_cancel_journey["elapsed"] < 10.0


def test_step_15_sdk_round_trip_matches_cli(operator_journey: dict[str, object]) -> None:
    sdk_result = operator_journey["sdk_result"]
    status = operator_journey["status"]
    assert sdk_result.id == operator_journey["job_id"]
    assert sdk_result.state.value == status["state"]


def test_journey_progress_is_reported(record_property) -> None:
    """Emit how many acceptance steps are live without gating on that count."""
    steps = [value for name, value in globals().items() if name.startswith("test_step_")]
    skipped = sum(
        1 for step in steps if any(mark.name == "skip" for mark in getattr(step, "pytestmark", []))
    )
    record_property("acceptance_steps_live", len(steps) - skipped)
    record_property("acceptance_steps_total", len(steps))
    assert len(steps) == 15
