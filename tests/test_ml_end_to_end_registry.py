"""Persistent registry-to-serving E2E contract."""
# ruff: noqa: E501

from studio_core import AssetId, AssetRef, AssetVersion, WorkspaceId
from studio_core.ml import (
    Experiment,
    ExperimentId,
    MetricValue,
    MLRunId,
    ModelEvaluation,
    ModelId,
    ModelVersion,
)
from studio_ml import (
    TrainingSpec,
    predict_registered_tabular,
    promote_registered_model,
    train_register_tabular,
)
from studio_storage import LocalArtifactStore

from tests.test_ml_foundation import _stores


def test_train_register_evaluate_promote_and_score_from_artifact_store(tmp_path) -> None:
    database = tmp_path / "ronin.sqlite3"
    registry, _ = _stores(database)
    artifacts = LocalArtifactStore(tmp_path / "artifacts")
    workspace = WorkspaceId("ws-1")
    dataset = AssetRef(AssetId("dataset-1"), AssetVersion("v1"))
    rows = [{"x": value, "target": value % 2} for value in range(1, 21)]
    spec = TrainingSpec("classification", "logistic_regression", ("x",), "target")
    registry.put_experiment(
        workspace,
        Experiment(ExperimentId("churn"), "Churn search"),
        now="2026-09-12T00:00:00.000000Z",
    )
    model = train_register_tabular(
        registry,
        artifacts,
        workspace,
        rows,
        dataset=dataset,
        experiment_id=ExperimentId("churn"),
        run_id=MLRunId("churn-trial-1"),
        model_id=ModelId("churn"),
        model_version=ModelVersion("1"),
        source_revision="source",
        execution_ref="local",
        spec=spec,
        now="2026-09-12T00:00:00.000000Z",
    )
    registry.record_evaluation(
        workspace,
        ModelEvaluation(
            model.model_id,
            model.version,
            dataset,
            "passed",
            (MetricValue("accuracy", 1.0),),
            "eval-1",
        ),
        now="2026-09-12T00:00:00.000000Z",
    )
    promoted = promote_registered_model(
        registry, workspace, model.model_id, model.version, now="2026-09-12T00:00:00.000000Z"
    )
    artifact = artifacts.get_bytes_by_storage_ref(model.artifact_ref, digest=model.artifact_digest)
    predictions = predict_registered_tabular(
        registry, workspace, model.model_id, model.version, artifact, [{"x": 21}]
    )
    assert promoted.stage == "champion"
    assert len(predictions) == 1
