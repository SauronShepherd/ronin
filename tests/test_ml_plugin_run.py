"""Machine Learning Studio run-route contract tests."""
# ruff: noqa: E501

import pytest
from studio_core import WorkspaceId
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_ml.domain import FeatureSpec, Lab
from studio_ml.plugin import MachineLearningStudioPlugin
from studio_ml.services import InMemoryMLLabStore, LabService


def test_plugin_run_route_returns_metrics() -> None:
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
    result = plugin.run_lab(
        "ws", "churn", body={"rows": [{"x": n, "target": n % 2} for n in range(1, 21)]}
    )
    assert result["lab_id"] == "churn"
    assert "metrics" in result


def test_plugin_run_route_rejects_non_object_rows() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._labs = LabService(InMemoryMLLabStore())
    with pytest.raises(ValueError, match="rows"):
        plugin.run_lab("ws", "missing", body={"rows": ["not-a-row"]})
