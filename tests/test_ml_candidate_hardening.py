from __future__ import annotations

from unittest.mock import patch

import pytest
from studio_core import AssetId, AssetRef, AssetVersion, WorkspaceId
from studio_core.ml import Experiment, ExperimentId, MLRunId, ModelId, ModelVersion
from studio_core.plugins import PipelineStageContribution
from studio_ml.plugin import MachineLearningStudioPlugin
from studio_ml.plugin_stage_runtime import (
    PluginStageExecutionError,
    execute_plugin_stage,
)
from studio_ml.runtime import TrainingSpec
from studio_ml.service import (
    deploy_registered_model,
    record_deployment_request,
    rollback_model_deployment,
    train_register_tabular,
)
from studio_storage import LocalArtifactStore

from tests.test_ml_foundation import _stores


def test_deployment_pins_predicts_and_rolls_back_without_repinning(tmp_path) -> None:
    registry, _catalog = _stores(tmp_path / "ronin.sqlite3")
    artifacts = LocalArtifactStore(tmp_path / "artifacts")
    workspace = WorkspaceId("ws-1")
    registry.put_experiment(
        workspace,
        Experiment(ExperimentId("exp-1"), "Deployment test"),
        now="2026-10-23T00:00:00.000000Z",
    )
    model = train_register_tabular(
        registry,
        artifacts,
        workspace,
        [{"x": value, "target": value % 2} for value in range(1, 21)],
        dataset=AssetRef(AssetId("dataset-1"), AssetVersion("v1")),
        experiment_id=ExperimentId("exp-1"),
        run_id=MLRunId("run-1"),
        model_id=ModelId("churn"),
        model_version=ModelVersion("1"),
        source_revision="source",
        execution_ref="execution-1",
        spec=TrainingSpec("classification", "logistic_regression", ("x",), "target"),
        now="2026-10-23T00:00:00.000000Z",
    )
    deployment = deploy_registered_model(
        registry,
        artifacts,
        workspace,
        "local-churn",
        model.model_id,
        model.version,
        now="2026-10-23T00:00:00.000000Z",
    )
    assert deployment.status == "ready"
    assert deployment.readiness == "ready"
    assert (
        deploy_registered_model(
            registry,
            artifacts,
            workspace,
            "local-churn",
            model.model_id,
            model.version,
            now="2026-10-23T00:00:01.000000Z",
        )
        == deployment
    )

    plugin = MachineLearningStudioPlugin()
    plugin._registry = registry
    plugin._artifacts = artifacts
    try:
        response = plugin.predict_deployment(
            "local-churn",
            "ws-1",
            body={"rows": [{"x": 21}]},
        )
        assert response["deployment_id"] == "local-churn"
        assert len(response["predictions"]) == 1
        assert response["telemetry"]["request_count"] == 1
    finally:
        plugin._coordinator.close()

    rolled_back = rollback_model_deployment(
        registry,
        workspace,
        "local-churn",
        now="2026-10-23T00:00:02.000000Z",
    )
    assert rolled_back.status == "rolled_back"
    assert rolled_back.readiness == "unready"
    assert (
        rollback_model_deployment(
            registry,
            workspace,
            "local-churn",
            now="2026-10-23T00:00:03.000000Z",
        )
        == rolled_back
    )
    with pytest.raises(ValueError, match="already pinned"):
        deploy_registered_model(
            registry,
            artifacts,
            workspace,
            "local-churn",
            model.model_id,
            model.version,
            endpoint="other",
            now="2026-10-23T00:00:04.000000Z",
        )
    with pytest.raises(ValueError, match="not ready"):
        record_deployment_request(
            registry,
            workspace,
            "local-churn",
            success=True,
            now="2026-10-23T00:00:05.000000Z",
        )


def test_plugin_stage_runtime_validates_bounded_canonical_exchange() -> None:
    stage = PipelineStageContribution(
        plugin_id="com.example.ml",
        stage_id="com.example.ml/score",
        version=1,
        plugin_version="1.0.0",
        distribution_digest="a" * 64,
        executor_image="registry.example/ml@sha256:" + "b" * 64,
        operation_id="score.v1",
        input_ports={"rows": ("ml.rows", 1, 1)},
        output_type="ml.metrics",
        config_fields=("threshold",),
        permissions=("artifact:read", "artifact:write"),
        effect="artifact_write",
    )
    captured: dict[str, object] = {}

    def fake_invoke(_stage, payload, _cancellation):
        captured.update(payload)
        return {
            "output": {"score": 0.9},
            "artifacts": [
                {
                    "name": "metrics.json",
                    "media_type": "application/json",
                    "data_base64": "eyJzY29yZSI6MC45fQ==",
                }
            ],
        }

    with patch("studio_ml.plugin_stage_runtime._invoke", side_effect=fake_invoke):
        result = execute_plugin_stage(
            stage,
            config={"threshold": 0.5},
            inputs={"rows": {"count": 20}},
            artifacts={"input.json": b"{}"},
        )
    assert captured["schema"] == "ronin.ml-plugin-stage-request/v1"
    assert result.value == {"score": 0.9}
    assert result.artifacts[0].data == b'{"score":0.9}'

    with (
        patch(
            "studio_ml.plugin_stage_runtime._invoke",
            return_value={
                "output": {"score": 0.9},
                "artifacts": [{"name": "bad", "media_type": "text/plain", "data_base64": "%%%"}],
            },
        ),
        pytest.raises(PluginStageExecutionError, match="invalid base64"),
    ):
        execute_plugin_stage(stage, config={"threshold": 0.5}, inputs={"rows": {}})
