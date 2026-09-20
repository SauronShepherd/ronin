"""Asynchronous ML Studio lifecycle tests."""
# ruff: noqa: E501

import time

from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_ml.domain import FeatureSpec, Lab
from studio_ml.orchestration import LocalExecutionCoordinator


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
        deadline = time.time() + 30
        while (
            coordinator.status("run-1").state not in {"succeeded", "failed"}
            and time.time() < deadline
        ):
            time.sleep(0.01)
        assert coordinator.status("run-1").state == "succeeded"
    finally:
        coordinator.close()
