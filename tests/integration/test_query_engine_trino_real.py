from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Mapping
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from studio_data_engineering import (
    QueryEngineRuntimeProvider,
    QueryFluxWorkerRunner,
    SqliteQueryEvidenceReferenceStore,
    SqliteQueryFluxExecutionStore,
    execute_query,
)
from studio_query_engine import (
    DiscoveredEngine,
    EngineCapabilities,
    EngineHandshake,
    QueryExecutionPolicy,
    QueryRequest,
    QueryFluxTrinoTransport,
    TrinoHttpTransport,
)
from studio_orchestrator import Instant, Job, JobId, JobState, Run, RunId, RunState
from studio_storage import LocalArtifactStore, SqliteJobStore

_TRINO_URL = os.environ.get("RONIN_TRINO_TEST_URL")
pytestmark = pytest.mark.skipif(
    not _TRINO_URL,
    reason="real Trino query binding qualification requires RONIN_TRINO_TEST_URL",
)


class _LocalTrinoHttpClient:
    def request(self, method: str, url: str, *, body: str | None = None) -> Mapping[str, object]:
        parsed = urlsplit(url)
        if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("real Trino test client only accepts loopback HTTP")
        connection = HTTPConnection(parsed.hostname, parsed.port or 80, timeout=15)
        try:
            connection.request(
                method,
                parsed.path + (f"?{parsed.query}" if parsed.query else ""),
                body=body,
                headers={"X-Trino-User": "ronin-qualification"},
            )
            response = connection.getresponse()
            payload = json.loads(response.read())
            if response.status != 200:
                raise RuntimeError(f"Trino returned HTTP {response.status}: {payload}")
        finally:
            connection.close()
        if not isinstance(payload, Mapping):
            raise AssertionError("Trino response must be a JSON object")
        return payload


def test_trino_real_prepared_scalar_bindings() -> None:
    assert _TRINO_URL is not None
    parsed = urlsplit(_TRINO_URL)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("real Trino qualification URL must use local loopback HTTP")
    base_url = _TRINO_URL if _TRINO_URL.endswith("/") else f"{_TRINO_URL}/"
    transport = TrinoHttpTransport(_LocalTrinoHttpClient(), base_url=base_url)
    request = QueryRequest(
        "SELECT CAST(? AS VARCHAR), CAST(? AS BIGINT), CAST(? AS BOOLEAN), "
        "CAST(? AS DOUBLE), COALESCE(CAST(? AS VARCHAR), CAST(NULL AS VARCHAR))",
        "trino-qualification",
        parameters=("O'Reilly", 2**63 - 1, True, 2.5, None),
    )
    handle, next_uri = transport.submit(request)
    pages = []

    for _ in range(100):
        status, page, following = transport.poll(handle, next_uri)
        if page is not None:
            pages.append(page)
        if status.state in {"succeeded", "failed", "cancelled"}:
            break
        assert following is not None
        next_uri = following
    else:
        transport.cancel(handle)
        pytest.fail("Trino query did not reach a terminal state within 100 polls")

    assert status.state == "succeeded", status.message
    assert pages
    assert all(page.columns == pages[0].columns for page in pages)
    assert tuple(row for page in pages for row in page.rows) == (
        ("O'Reilly", 2**63 - 1, True, 2.5, None),
    )


def test_trino_real_result_byte_budget_accepts_exact_limit_and_rejects_one_byte_less(
    tmp_path: Path,
) -> None:
    assert _TRINO_URL is not None
    base_url = _TRINO_URL if _TRINO_URL.endswith("/") else f"{_TRINO_URL}/"
    transport = TrinoHttpTransport(_LocalTrinoHttpClient(), base_url=base_url)
    provider = QueryEngineRuntimeProvider(
        DiscoveredEngine(
            EngineHandshake(
                "trino",
                "484",
                EngineCapabilities((("cancel", True), ("parameter_binding", True))),
                True,
            ),
            ("trino",),
            "ready",
        ),
        QueryExecutionPolicy((("trino", ("trino",)),), required_capability="cancel"),
    )
    expected = {"columns": ["_col0"], "rows": [["ok"]], "row_count": 1}
    exact_limit = len(json.dumps(expected, separators=(",", ":")).encode("utf-8"))

    accepted = execute_query(
        provider,
        transport,
        LocalArtifactStore(tmp_path / "accepted-artifacts"),
        QueryRequest(
            "SELECT CAST(? AS VARCHAR)",
            "trino",
            parameters=("ok",),
            max_result_bytes=exact_limit,
        ),
        engine="trino",
        project_id="qualification-project",
        run_id="result-budget-accepted",
        attempt_id="attempt-1",
    )
    rejected = execute_query(
        provider,
        transport,
        LocalArtifactStore(tmp_path / "rejected-artifacts"),
        QueryRequest(
            "SELECT CAST(? AS VARCHAR)",
            "trino",
            parameters=("ok",),
            max_result_bytes=exact_limit - 1,
        ),
        engine="trino",
        project_id="qualification-project",
        run_id="result-budget-rejected",
        attempt_id="attempt-1",
    )

    assert accepted.status.state == "succeeded"
    assert accepted.page is not None
    assert accepted.page.rows == (("ok",),)
    assert rejected.status.state == "failed"
    assert rejected.status.message == "query result exceeds the configured byte limit"
    assert rejected.page is None


def test_queryflux_worker_runner_real_trino_persists_terminal_evidence(tmp_path: Path) -> None:
    assert _TRINO_URL is not None
    base_url = _TRINO_URL if _TRINO_URL.endswith("/") else f"{_TRINO_URL}/"
    transport = QueryFluxTrinoTransport(_LocalTrinoHttpClient(), base_url=base_url)
    provider = QueryEngineRuntimeProvider(
        DiscoveredEngine(
            EngineHandshake(
                "queryflux",
                "484",
                EngineCapabilities((
                    ("cancel", True),
                    ("parameter_binding", True),
                )),
                True,
            ),
            ("trino",),
            "ready",
        ),
        QueryExecutionPolicy((("queryflux", ("trino",)),), required_capability="cancel"),
    )
    references = SqliteQueryEvidenceReferenceStore(tmp_path / "ronin.db")
    executions = SqliteQueryFluxExecutionStore(tmp_path / "ronin.db")
    runner = QueryFluxWorkerRunner(
        provider,
        transport,
        LocalArtifactStore(tmp_path / "artifacts"),
        references,
        executions,
    )
    result = runner(
        {
            "workspace_id": "workspace-real",
            "project_id": "project-real",
            "run_id": "run-real-worker",
            "attempt_id": "attempt-1",
            "sql": "SELECT CAST(? AS VARCHAR), CAST(? AS BIGINT)",
            "engine": "trino",
            "translation_policy": "native_only",
            "max_rows": 100,
            "page_size": 50,
            "max_result_bytes": 4096,
            "parameters": ["worker", 7],
        }
    )
    assert result["state"] == "succeeded"
    assert result["row_count"] == 1
    execution = executions.get("workspace-real", "project-real", "run-real-worker", "attempt-1")
    assert execution is not None and execution.state == "succeeded"
    assert references.list_evidence_references()[0]["digest"] == result["evidence"]["digest"]


def test_queryflux_real_worker_process_sigkill_reclaims_without_duplicate(tmp_path: Path) -> None:
    assert _TRINO_URL is not None
    fixed = Instant("2026-11-12T00:00:00.000000Z")
    database = tmp_path / "ronin.sqlite3"
    store = SqliteJobStore(database, migration_now=fixed)
    payload = json.dumps(
        {
            "workspace_id": "workspace-process",
            "project_id": "project-process",
            "run_id": "run-process",
            "attempt_id": "attempt-1",
            "sql": "SELECT CAST(? AS VARCHAR)",
            "engine": "trino",
            "translation_policy": "native_only",
            "max_rows": 10,
            "page_size": 10,
            "max_result_bytes": 4096,
            "parameters": ["process-recovery"],
        },
        separators=(",", ":"),
    )
    store.create_job(
        Job(
            id=JobId("job-queryflux-process"),
            project_id="project-process",
            idempotency_key="queryflux-process-recovery",
            request_digest="c" * 64,
            state=JobState.QUEUED,
            created_at=fixed,
            updated_at=fixed,
            target="data-engineering.queryflux-execution.v1",
            parameters_json=payload,
        ),
        Run(
            id=RunId("run-process"),
            job_id=JobId("job-queryflux-process"),
            ordinal=1,
            state=RunState.PENDING,
            not_before=fixed,
            created_at=fixed,
            updated_at=fixed,
        ),
    )
    env = os.environ.copy()
    env.update(
        {
            "RONIN_DB": str(database),
            "RONIN_WORKSPACE": str(tmp_path),
            "RONIN_STORAGE_BACKEND": "sqlite",
            "RONIN_IMAGE": "sha256:" + "1" * 64,
            "RONIN_QUERYFLUX_URL": _TRINO_URL if _TRINO_URL.endswith("/") else _TRINO_URL + "/",
            "RONIN_WORKER_LEASE_SECONDS": "2",
            "RONIN_WORKER_EXCLUDED_TARGETS": "",
        }
    )
    command = [sys.executable, "-m", "studio_cli.entrypoint", "worker"]
    first = subprocess.Popen(command, cwd=str(Path.cwd()), env=env)
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            current = store.get_job(JobId("job-queryflux-process"))
            if current is not None and current.state is JobState.RUNNING:
                break
            if first.poll() is not None:
                raise AssertionError(f"worker exited before claim: {first.returncode}")
            time.sleep(0.1)
        else:
            raise AssertionError("worker did not claim QueryFlux job")
        first.kill()
        first.wait(timeout=10)
        time.sleep(2.5)
        second = subprocess.Popen(command, cwd=str(Path.cwd()), env=env)
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                current = store.get_job(JobId("job-queryflux-process"))
                if current is not None and current.state is JobState.SUCCEEDED:
                    break
                if second.poll() is not None:
                    raise AssertionError(f"replacement worker exited: {second.returncode}")
                time.sleep(0.2)
            else:
                raise AssertionError("replacement worker did not complete QueryFlux job")
        finally:
            second.terminate()
            second.wait(timeout=10)
    finally:
        if first.poll() is None:
            first.kill()
            first.wait(timeout=10)
    final = store.get_job(JobId("job-queryflux-process"))
    assert final is not None and final.state is JobState.SUCCEEDED
    events = store.read_events(RunId("run-process"), since=0)
    assert sum(event.kind == "worker.attempt.succeeded" for event in events) == 1
