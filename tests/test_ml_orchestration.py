"""Asynchronous ML Studio lifecycle tests."""
# ruff: noqa: E501

import os
import time
from threading import Event, Thread
from types import SimpleNamespace

import pytest
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_ml.domain import FeatureSpec, Lab
from studio_ml.orchestration import InMemoryExecutionStore, LocalExecutionCoordinator

LOCAL_ML_TIMEOUT = 90 if os.name == "nt" else 30


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
        coordinator.submit("run-1", lab, [{"x": n, "target": n % 2} for n in range(1, 21)])
        # First-use sklearn imports can exceed five seconds on a cold Windows host.
        deadline = time.time() + LOCAL_ML_TIMEOUT
        while (
            coordinator.status("run-1").state not in {"succeeded", "failed"}
            and time.time() < deadline
        ):
            time.sleep(0.01)
        assert coordinator.status("run-1").state == "succeeded"
    finally:
        coordinator.close()


def test_local_coordinator_executes_clustering_lab() -> None:
    lab = Lab(
        id="clusters",
        name="Clusters",
        project_id="project",
        dataset=AssetRef("asset", AssetVersion("v1")),
        target=None,
        task="clustering",
        features=(FeatureSpec("x"),),
    )
    coordinator = LocalExecutionCoordinator()
    try:
        coordinator.submit("cluster-run", lab, [{"x": value} for value in (0.0, 0.1, 9.9, 10.0)])
        for _ in range(100):
            snapshot = coordinator.status("cluster-run")
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
        coordinator.submit("run-cancel", lab, [{"x": n, "target": n % 2} for n in range(1, 21)])
        outcome: list[object] = []

        def cancel() -> None:
            try:
                outcome.append(coordinator.cancel("run-cancel"))
            except Exception as exc:  # pragma: no cover - surfaced by the assertion below
                outcome.append(exc)

        thread = Thread(target=cancel, daemon=True)
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive(), "cancel deadlocked while reading its own status"
        assert len(outcome) == 1
        assert not isinstance(outcome[0], Exception), outcome[0]
        assert coordinator.status("run-cancel").state in {
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
        coordinator.submit("run-cancel-race", lab, [{"x": 1, "target": 1}])
        assert started.wait(timeout=5), "runner did not start"

        cancelled = coordinator.cancel("run-cancel-race")
        assert cancelled.state == "cancelled"

        release_failure.set()
        future = coordinator._futures["run-cancel-race"]
        with pytest.raises(ValueError, match="runner failed after cancellation"):
            future.result(timeout=5)

        assert coordinator.status("run-cancel-race").state == "cancelled"
        persisted = store.get("run-cancel-race")
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
        coordinator.submit("run-cancel-success", lab, [{"x": 1, "target": 1}])
        assert started.wait(timeout=5), "runner did not start"
        assert coordinator.cancel("run-cancel-success").state == "cancelled"

        release_success.set()
        coordinator._futures["run-cancel-success"].result(timeout=5)

        assert coordinator.status("run-cancel-success").state == "cancelled"
        persisted = store.get("run-cancel-success")
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
        coordinator.submit("run-active", lab, [{"x": 1, "target": 1}])
        assert started.wait(timeout=5), "first runner did not start"

        coordinator.submit("run-queued", lab, [{"x": 2, "target": 0}])
        queued_future = coordinator._futures["run-queued"]
        assert coordinator.status("run-queued").state == "queued"
        assert coordinator.cancel("run-queued").state == "cancelled"
        assert queued_future.cancelled()

        release.set()
        coordinator._futures["run-active"].result(timeout=5)

        assert calls == [1]
        assert coordinator.status("run-queued").state == "cancelled"
    finally:
        release.set()
        coordinator.close()
