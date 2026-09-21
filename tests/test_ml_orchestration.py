"""Asynchronous ML Studio lifecycle tests."""
# ruff: noqa: E501

import time
import os

from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_ml.domain import FeatureSpec, Lab
from studio_ml.orchestration import LocalExecutionCoordinator

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
        id="clusters", name="Clusters", project_id="project",
        dataset=AssetRef("asset", AssetVersion("v1")), target=None,
        task="clustering", features=(FeatureSpec("x"),),
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
