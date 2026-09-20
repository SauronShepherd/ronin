"""Async execution route contract tests."""

# ruff: noqa: E501
import time

import pytest
from studio_core import WorkspaceId
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_ml.domain import FeatureSpec, Lab
from studio_ml.plugin import MachineLearningStudioPlugin
from studio_ml.services import InMemoryMLLabStore, LabService


def test_submit_and_poll_execution() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._labs = LabService(InMemoryMLLabStore())
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    plugin._labs.create(WorkspaceId("ws"), lab)
    submitted = plugin.submit_execution(
        "ws",
        "churn",
        body={"run_id": "async-1", "rows": [{"x": n, "target": n % 2} for n in range(1, 21)]},
    )
    assert submitted["run_id"] == "async-1"
    deadline = time.time() + 30
    state = plugin.execution_status("async-1")["state"]
    while state not in {"succeeded", "failed"} and time.time() < deadline:
        time.sleep(0.01)
        state = plugin.execution_status("async-1")["state"]
    assert state == "succeeded"
    plugin._coordinator.close()


def test_quality_route_returns_blocking_findings() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._labs = LabService(InMemoryMLLabStore())
    lab = Lab(
        "quality", "Quality", "crm", AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target", "classification", (FeatureSpec("x"),),
    )
    plugin._labs.create(WorkspaceId("ws"), lab)
    report = plugin.quality_check(
        "ws", "quality", body={"rows": [{"x": 1, "target": "only"}] * 3}
    )
    assert report["passed"] is False
    assert report["failures"]
    plugin._coordinator.close()


def test_compare_route_ranks_trials_deterministically() -> None:
    plugin = MachineLearningStudioPlugin()
    result = plugin.compare_trials(
        "ws", "lab", body={
            "spec": {"mode": "grid", "metric": "accuracy", "direction": "maximize"},
            "trials": [
                {"parameters": {"C": 1}, "metrics": {"accuracy": 0.8}},
                {"parameters": {"C": 2}, "metrics": {"accuracy": 0.9}},
            ],
        },
    )
    assert result["items"][0]["metrics"]["accuracy"] == 0.9
    plugin._coordinator.close()


def test_search_route_executes_grid_trials() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._labs = LabService(InMemoryMLLabStore())
    lab = Lab(
        "search", "Search", "crm", AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target", "classification", (FeatureSpec("x"),),
    )
    plugin._labs.create(WorkspaceId("ws"), lab)
    result = plugin.search_trials(
        "ws", "search", body={
            "spec": {"mode": "grid", "parameters": [{"name": "seed", "values": [1, 2]}], "metric": "accuracy"},
            "rows": [{"x": n, "target": n % 2} for n in range(1, 21)],
        },
    )
    assert len(result["items"]) == 2
    assert all("metrics" in item for item in result["items"])
    plugin._coordinator.close()


def test_search_registration_requires_persistent_services() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._labs = LabService(InMemoryMLLabStore())
    lab = Lab(
        "search-register", "Search", "crm", AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target", "classification", (FeatureSpec("x"),),
    )
    plugin._labs.create(WorkspaceId("ws"), lab)
    with pytest.raises(ValueError, match="artifact_store"):
        plugin.search_trials(
            "ws", "search-register", body={
                "spec": {"mode": "single"}, "register": {"model_id": "churn"},
                "rows": [{"x": n, "target": n % 2} for n in range(1, 21)],
            },
        )
    plugin._coordinator.close()
