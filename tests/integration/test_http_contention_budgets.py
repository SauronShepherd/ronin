from __future__ import annotations

import math
import time
from pathlib import Path
from threading import Event, Thread

from pyronin import HTTPTransport, Ronin
from studio_execution import DurableExecutionService
from studio_orchestrator import Instant, Job, JobId
from studio_server import RoninHTTPServer
from studio_storage import SqliteJobStore

_MIGRATION_NOW = Instant("2026-09-07T07:30:00.000000Z")
_AUTHORIZATION = "".join(("budget", "-qualification"))
_POST_P95_BUDGET_MS = 100.0
_GET_P95_BUDGET_MS = 30.0


class _OneBlockedStatusSqliteStore(SqliteJobStore):
    """Occupy one bounded store worker while all other calls use real SQLite."""

    def __init__(self, path: Path) -> None:
        super().__init__(path, migration_now=_MIGRATION_NOW)
        self.block_started = Event()
        self.release_block = Event()

    def get_job(self, job_id: JobId) -> Job | None:
        if job_id == JobId("contention-blocker"):
            self.block_started.set()
            if not self.release_block.wait(timeout=5.0):
                raise RuntimeError("bounded-contention status probe was not released")
        return super().get_job(job_id)


def _p95_ms(samples_seconds: list[float]) -> float:
    ordered = sorted(samples_seconds)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index] * 1000.0


def test_real_http_submit_status_meet_p95_budgets_under_bounded_contention(
    tmp_path: Path,
) -> None:
    store = _OneBlockedStatusSqliteStore(tmp_path / "ronin.db")
    service = DurableExecutionService(store, max_workers=2, max_in_flight=4)
    server = RoninHTTPServer(("127.0.0.1", 0), service, token=_AUTHORIZATION)
    server_thread = Thread(target=server.serve_forever, name="ronin-http-budget", daemon=True)
    server_thread.start()

    blocker_result: list[object] = []

    def block_one_store_worker() -> None:
        blocker_result.append(server.application.status("contention-blocker"))

    blocker = Thread(target=block_one_store_worker, name="ronin-store-contention", daemon=True)

    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        transport = HTTPTransport(
            base_url,
            token=_AUTHORIZATION,
            allow_insecure_localhost=True,
            max_retries=0,
        )
        client = Ronin(transport=transport)

        seed = client.submit(
            project="examples/demo",
            target="notebooks/etl",
            parameters={"qualification": "warmup"},
            idempotency_key="budget-warmup",
        )
        for _ in range(5):
            assert client.get_job(seed.id).id == seed.id

        blocker.start()
        assert store.block_started.wait(timeout=1.0)

        post_samples: list[float] = []
        for index in range(20):
            started = time.perf_counter()
            handle = client.submit(
                project="examples/demo",
                target="notebooks/etl",
                parameters={"sample": index},
                idempotency_key=f"budget-post-{index}",
            )
            post_samples.append(time.perf_counter() - started)
            assert handle.id

        get_samples: list[float] = []
        for _ in range(50):
            started = time.perf_counter()
            observed = client.get_job(seed.id)
            get_samples.append(time.perf_counter() - started)
            assert observed.id == seed.id

        post_p95_ms = _p95_ms(post_samples)
        get_p95_ms = _p95_ms(get_samples)
        assert post_p95_ms < _POST_P95_BUDGET_MS, (
            f"POST /v1/jobs p95 {post_p95_ms:.3f} ms exceeds {_POST_P95_BUDGET_MS:.0f} ms budget"
        )
        assert get_p95_ms < _GET_P95_BUDGET_MS, (
            f"GET /v1/jobs/{{id}} p95 {get_p95_ms:.3f} ms exceeds "
            f"{_GET_P95_BUDGET_MS:.0f} ms budget"
        )
    finally:
        store.release_block.set()
        blocker.join(timeout=5.0)
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5.0)

    assert not blocker.is_alive()
    assert blocker_result == [None]
    assert not server_thread.is_alive()
