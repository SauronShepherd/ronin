"""Asynchronous ML Studio lifecycle tests."""
# ruff: noqa: E501

import hashlib
import os
import time
from threading import Event, Thread
from types import SimpleNamespace

import pytest
from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_execution import DurableExecutionService
from studio_ml.domain import FeatureSpec, Lab
from studio_ml.orchestration import (
    ExecutionConflict,
    ExecutionSnapshot,
    InMemoryExecutionStore,
    JobStoreExecutionStore,
    LocalExecutionCoordinator,
)
from studio_orchestrator import Instant
from studio_storage import SqliteJobStore

LOCAL_ML_TIMEOUT = 90 if os.name == "nt" else 30
_MIGRATION_NOW = Instant("2026-10-19T00:00:00.000000Z")


def _active_future(coordinator: LocalExecutionCoordinator, key: tuple[str, str]):
    deadline = time.monotonic() + 5
    while key not in coordinator._futures and time.monotonic() < deadline:
        time.sleep(0.001)
    return coordinator._futures[key]


def test_local_coordinator_reaches_terminal_state() -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    coordinator = LocalExecutionCoordinator()
    try:
        coordinator.submit("ws", "run-1", lab, [{"x": n, "target": n % 2} for n in range(1, 21)])
        # First-use sklearn imports can exceed five seconds on a cold Windows host.
        deadline = time.time() + LOCAL_ML_TIMEOUT
        while (
            coordinator.status("ws", "run-1").state not in {"succeeded", "failed"}
            and time.time() < deadline
        ):
            time.sleep(0.01)
        assert coordinator.status("ws", "run-1").state == "succeeded"
    finally:
        coordinator.close()


def test_ml_execution_uses_shared_sqlite_job_lifecycle_and_persists_result(tmp_path) -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )

    class ImmediateRunner:
        def run(self, _lab, _rows):
            return SimpleNamespace(to_payload=lambda: {"accuracy": 1.0})

    jobs = SqliteJobStore(tmp_path / "jobs.sqlite", migration_now=_MIGRATION_NOW)
    service = DurableExecutionService(jobs)
    coordinator = LocalExecutionCoordinator(
        runner=ImmediateRunner(), store=JobStoreExecutionStore(service)
    )
    try:
        coordinator.submit("workspace-a", "shared-id", lab, [{"x": 1, "target": 1}])
        coordinator.submit("workspace-b", "shared-id", lab, [{"x": 2, "target": 0}])
        deadline = time.time() + 10
        while time.time() < deadline:
            states = {
                coordinator.status(workspace, "shared-id").state
                for workspace in ("workspace-a", "workspace-b")
            }
            if states == {"succeeded"}:
                break
            time.sleep(0.01)
        assert states == {"succeeded"}
        assert coordinator.status("workspace-a", "shared-id").result_payload == {"accuracy": 1.0}
        with pytest.raises(ExecutionConflict, match="already exists"):
            coordinator.submit("workspace-a", "shared-id", lab, [{"x": 3, "target": 1}])
        first_id, _ = JobStoreExecutionStore._ids("workspace-a", "shared-id")
        second_id, _ = JobStoreExecutionStore._ids("workspace-b", "shared-id")
        assert first_id != second_id
    finally:
        coordinator.close()
        import asyncio

        asyncio.run(service.aclose())


def test_shared_job_store_cancel_fences_ml_worker_write(tmp_path) -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    jobs = SqliteJobStore(tmp_path / "jobs.sqlite", migration_now=_MIGRATION_NOW)
    service = DurableExecutionService(jobs)
    adapter = JobStoreExecutionStore(service)
    try:
        adapter.create(
            ExecutionSnapshot(
                run_id="cancel-me",
                state="queued",
                workspace_id="workspace-a",
                lab_id=lab.id,
                lab_digest=lab.digest,
                request_digest=hashlib.sha256(b"request").hexdigest(),
                lab_json=lab.to_json(),
                rows_json=encode_canonical_json([{"x": 1, "target": 1}]).decode(),
            )
        )
        claim = adapter.claim_next("worker-a")
        assert claim is not None
        cancelled = adapter.cancel("workspace-a", "cancel-me")
        assert cancelled.state == "cancelled"
        with pytest.raises(Exception, match="lease|ownership|cancel|terminal"):
            adapter.finish_claim(claim, state="succeeded", result_payload={"late": True})
        status = adapter.get("workspace-a", "cancel-me")
        assert status is not None
        assert status.state == "cancelled"
    finally:
        import asyncio

        asyncio.run(service.aclose())


def test_shared_job_store_reopens_and_idempotent_retry_does_not_duplicate_job(tmp_path) -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )

    class ImmediateRunner:
        def run(self, _lab, _rows):
            return SimpleNamespace(to_payload=lambda: {"recovered": True})

    path = tmp_path / "jobs.sqlite"
    service = DurableExecutionService(SqliteJobStore(path, migration_now=_MIGRATION_NOW))
    adapter = JobStoreExecutionStore(service)
    rows = [{"x": 1, "target": 1}]
    request_digest = hashlib.sha256(
        encode_canonical_json({"lab": lab.to_payload(), "rows": rows})
    ).hexdigest()
    first = adapter.create(
        ExecutionSnapshot(
            run_id="recoverable",
            state="queued",
            workspace_id="workspace-a",
            lab_id=lab.id,
            lab_digest=lab.digest,
            request_digest=request_digest,
            lab_json=lab.to_json(),
            rows_json=encode_canonical_json(rows).decode(),
        )
    )
    import asyncio

    asyncio.run(service.aclose())

    reopened_service = DurableExecutionService(SqliteJobStore(path, migration_now=_MIGRATION_NOW))
    reopened_adapter = JobStoreExecutionStore(reopened_service)
    coordinator = LocalExecutionCoordinator(runner=ImmediateRunner(), store=reopened_adapter)
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            recovered = coordinator.status("workspace-a", "recoverable")
            if recovered.state in {"succeeded", "failed"}:
                break
            time.sleep(0.01)
        assert recovered.state == "succeeded"
        replay = reopened_adapter.create(
            ExecutionSnapshot(
                run_id="recoverable",
                state="queued",
                workspace_id="workspace-a",
                lab_id=lab.id,
                lab_digest=lab.digest,
                request_digest=first.request_digest,
                lab_json=lab.to_json(),
                rows_json=encode_canonical_json(rows).decode(),
            )
        )
        assert replay.state == "succeeded"
        from studio_orchestrator import JobState

        page = asyncio.run(
            reopened_service.list_jobs(
                project_id="workspace-a",
                project_ids=None,
                state=JobState.SUCCEEDED,
                limit=10,
                cursor=None,
            )
        )
        assert len(page.items) == 1
    finally:
        coordinator.close()
        asyncio.run(reopened_service.aclose())


def test_shared_job_store_preserves_failure_reason(tmp_path) -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )

    class FailingRunner:
        def run(self, _lab, _rows):
            raise RuntimeError("training failed with a useful reason")

    import asyncio

    service = DurableExecutionService(
        SqliteJobStore(tmp_path / "jobs.sqlite", migration_now=_MIGRATION_NOW)
    )
    coordinator = LocalExecutionCoordinator(
        runner=FailingRunner(), store=JobStoreExecutionStore(service)
    )
    try:
        coordinator.submit("workspace-a", "failed-run", lab, [{"x": 1, "target": 1}])
        deadline = time.time() + 5
        while time.time() < deadline:
            failed = coordinator.status("workspace-a", "failed-run")
            if failed.state in {"succeeded", "failed"}:
                break
            time.sleep(0.01)
        assert failed.state == "failed"
        assert failed.error == "training failed with a useful reason"
    finally:
        coordinator.close()
        asyncio.run(service.aclose())


def test_local_coordinator_scopes_duplicate_run_ids_and_rejects_changed_retries() -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    rows = [{"x": n, "target": n % 2} for n in range(1, 21)]
    coordinator = LocalExecutionCoordinator()
    try:
        first = coordinator.submit("workspace-a", "shared-run", lab, rows)
        again = coordinator.submit("workspace-a", "shared-run", lab, rows)
        other = coordinator.submit("workspace-b", "shared-run", lab, rows)
        assert first.request_digest == again.request_digest
        assert other.workspace_id == "workspace-b"
        with pytest.raises(ExecutionConflict, match="already exists"):
            coordinator.submit("workspace-a", "shared-run", lab, rows[:-1])

        deadline = time.time() + LOCAL_ML_TIMEOUT
        while time.time() < deadline:
            states = {
                coordinator.status("workspace-a", "shared-run").state,
                coordinator.status("workspace-b", "shared-run").state,
            }
            if states == {"succeeded"}:
                break
            time.sleep(0.01)
        assert coordinator.status("workspace-a", "shared-run").state == "succeeded"
        assert coordinator.status("workspace-b", "shared-run").state == "succeeded"
    finally:
        coordinator.close()


def test_local_coordinator_rejects_oversized_requests_before_persisting(monkeypatch) -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    monkeypatch.setattr("studio_ml.orchestration.MAX_EXECUTION_REQUEST_BYTES", 64)
    coordinator = LocalExecutionCoordinator()
    try:
        with pytest.raises(ValueError, match="exceeds 64 bytes"):
            coordinator.submit("ws", "oversized", lab, [{"x": "value" * 20}])
        assert coordinator._store.get("ws", "oversized") is None
    finally:
        coordinator.close()


def test_expired_execution_owner_is_fenced_from_late_completion() -> None:
    store = InMemoryExecutionStore()
    snapshot = ExecutionSnapshot(
        "fenced-run",
        "queued",
        workspace_id="ws",
        lab_id="lab",
        lab_digest="a" * 64,
        request_digest="b" * 64,
        lab_json="{}",
        rows_json="[]",
    )
    store.create(snapshot)
    first = store.claim(
        "ws",
        "fenced-run",
        "owner-1",
        now=Instant("2026-10-19T00:00:00.000000Z"),
        lease_until=Instant("2026-10-19T00:01:00.000000Z"),
    )
    assert first is not None
    second = store.claim(
        "ws",
        "fenced-run",
        "owner-2",
        now=Instant("2026-10-19T00:01:01.000000Z"),
        lease_until=Instant("2026-10-19T00:02:01.000000Z"),
    )
    assert second is not None
    assert second.fence > first.fence
    assert store.finish("ws", "fenced-run", "owner-1", first.fence, state="succeeded") is None
    assert store.finish("ws", "fenced-run", "owner-2", second.fence, state="succeeded") is not None


def test_local_coordinator_executes_clustering_lab() -> None:
    lab = Lab(
        id="clusters",
        name="Clusters",
        project_id="project",
        dataset=AssetRef(AssetId("asset"), AssetVersion("v1")),
        target=None,
        task="clustering",
        features=(FeatureSpec("x"),),
    )
    coordinator = LocalExecutionCoordinator()
    try:
        coordinator.submit(
            "ws", "cluster-run", lab, [{"x": value} for value in (0.0, 0.1, 9.9, 10.0)]
        )
        for _ in range(100):
            snapshot = coordinator.status("ws", "cluster-run")
            if snapshot.state == "succeeded":
                assert snapshot.result_payload is not None
                assert snapshot.result_payload["algorithm"] == "kmeans"
                return
            if snapshot.state == "failed":
                raise AssertionError(snapshot.error)
            import time

            time.sleep(0.01)
        raise AssertionError("clustering execution did not finish")
    finally:
        coordinator.close()


def test_local_coordinator_cancel_does_not_deadlock() -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    coordinator = LocalExecutionCoordinator()
    try:
        coordinator.submit(
            "ws", "run-cancel", lab, [{"x": n, "target": n % 2} for n in range(1, 21)]
        )
        outcome: list[object] = []

        def cancel() -> None:
            try:
                outcome.append(coordinator.cancel("ws", "run-cancel"))
            except Exception as exc:  # pragma: no cover - surfaced by the assertion below
                outcome.append(exc)

        thread = Thread(target=cancel, daemon=True)
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive(), "cancel deadlocked while reading its own status"
        assert len(outcome) == 1
        assert not isinstance(outcome[0], Exception), outcome[0]
        assert coordinator.status("ws", "run-cancel").state in {
            "cancelled",
            "succeeded",
            "failed",
        }
    finally:
        coordinator.close()


def test_cancel_remains_terminal_when_runner_fails_after_cancellation() -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    started = Event()
    release_failure = Event()

    class FailingRunner:
        def run(self, _lab, _rows):
            started.set()
            if not release_failure.wait(timeout=5):
                raise TimeoutError("test runner was not released")
            raise ValueError("runner failed after cancellation")

    store = InMemoryExecutionStore()
    coordinator = LocalExecutionCoordinator(runner=FailingRunner(), store=store)
    try:
        coordinator.submit("ws", "run-cancel-race", lab, [{"x": 1, "target": 1}])
        assert started.wait(timeout=5), "runner did not start"

        cancelled = coordinator.cancel("ws", "run-cancel-race")
        assert cancelled.state == "cancelled"

        future = _active_future(coordinator, ("ws", "run-cancel-race"))
        release_failure.set()
        with pytest.raises(ValueError, match="runner failed after cancellation"):
            future.result(timeout=5)

        assert coordinator.status("ws", "run-cancel-race").state == "cancelled"
        persisted = store.get("ws", "run-cancel-race")
        assert persisted is not None
        assert persisted.state == "cancelled"
    finally:
        release_failure.set()
        coordinator.close()


def test_cancelled_running_run_does_not_become_succeeded_on_late_success() -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    started = Event()
    release_success = Event()

    class BlockingRunner:
        def run(self, _lab, _rows):
            started.set()
            if not release_success.wait(timeout=5):
                raise TimeoutError("test runner was not released")
            return SimpleNamespace(to_payload=lambda: {"status": "completed"})

    store = InMemoryExecutionStore()
    coordinator = LocalExecutionCoordinator(runner=BlockingRunner(), store=store)
    try:
        coordinator.submit("ws", "run-cancel-success", lab, [{"x": 1, "target": 1}])
        assert started.wait(timeout=5), "runner did not start"
        assert coordinator.cancel("ws", "run-cancel-success").state == "cancelled"

        future = _active_future(coordinator, ("ws", "run-cancel-success"))
        release_success.set()
        future.result(timeout=5)

        assert coordinator.status("ws", "run-cancel-success").state == "cancelled"
        persisted = store.get("ws", "run-cancel-success")
        assert persisted is not None
        assert persisted.state == "cancelled"
    finally:
        release_success.set()
        coordinator.close()


def test_cancel_prevents_a_queued_run_from_starting() -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    started = Event()
    release = Event()
    calls: list[int] = []

    class BlockingRunner:
        def run(self, _lab, _rows):
            calls.append(len(calls) + 1)
            if len(calls) == 1:
                started.set()
                if not release.wait(timeout=5):
                    raise TimeoutError("test runner was not released")
            return SimpleNamespace(to_payload=lambda: {"calls": len(calls)})

    coordinator = LocalExecutionCoordinator(runner=BlockingRunner(), max_workers=1)
    try:
        coordinator.submit("ws", "run-active", lab, [{"x": 1, "target": 1}])
        assert started.wait(timeout=5), "first runner did not start"
        active_future = _active_future(coordinator, ("ws", "run-active"))

        coordinator.submit("ws", "run-queued", lab, [{"x": 2, "target": 0}])
        assert coordinator.status("ws", "run-queued").state == "queued"
        assert ("ws", "run-queued") not in coordinator._futures
        assert coordinator.cancel("ws", "run-queued").state == "cancelled"

        release.set()
        active_future.result(timeout=5)

        assert calls == [1]
        assert coordinator.status("ws", "run-queued").state == "cancelled"
    finally:
        release.set()
        coordinator.close()
