from pathlib import Path

import pytest

from studio_core import AssetId, AssetRef, AssetVersion, WorkspaceId
from studio_core.ml import ExperimentId, MLRunId, ModelId, ModelVersion
from studio_ml import TrainingSpec, predict_registered_tabular, predict_tabular, train_register_tabular, train_tabular
from studio_storage import LocalArtifactStore

pytest.importorskip("sklearn")


class _Registry:
    def __init__(self) -> None:
        self.run = None
        self.model = None

    def record_run(self, workspace_id, run, *, now):
        del workspace_id, now
        self.run = run
        return run

    def register_model(self, workspace_id, model, *, now):
        del workspace_id, now
        self.model = model
        return model

    def get_model(self, workspace_id, model_id, version):
        del workspace_id
        if self.model is None:
            return None
        if self.model.model_id == model_id and self.model.version == version:
            return self.model
        return None


def _classification_rows():
    return tuple(
        {"x": float(index), "y": float(index % 3), "label": "high" if index >= 10 else "low"}
        for index in range(20)
    )


def test_classification_training_and_prediction() -> None:
    trained = train_tabular(
        _classification_rows(),
        TrainingSpec("classification", "logistic_regression", ("x", "y"), "label", 0.25, 7),
    )
    assert dict(trained.metrics)["accuracy"] >= 0.0
    predicted = predict_tabular(trained.artifact_bytes, ({"x": 2.0, "y": 2.0},))
    assert len(predicted) == 1


def test_training_service_records_run_and_registered_digest(tmp_path: Path) -> None:
    registry = _Registry()
    artifacts = LocalArtifactStore(tmp_path / "artifacts")
    dataset = AssetRef(AssetId("dataset"), AssetVersion("v1"))
    model = train_register_tabular(
        registry,
        artifacts,
        WorkspaceId("workspace"),
        _classification_rows(),
        dataset=dataset,
        experiment_id=ExperimentId("experiment"),
        run_id=MLRunId("run"),
        model_id=ModelId("model"),
        model_version=ModelVersion("1"),
        source_revision="git:abc",
        execution_ref="job:1",
        spec=TrainingSpec("classification", "logistic_regression", ("x", "y"), "label", 0.25, 7),
        now="2026-09-13T10:00:00.000000Z",
    )
    assert registry.run is not None
    assert registry.model == model
    storage_ref = model.artifact_ref
    digest = storage_ref.rsplit("/", 1)[-1]
    artifact_path = tmp_path / "artifacts" / "sha256" / digest[:2] / digest
    data = artifact_path.read_bytes()
    predicted = predict_registered_tabular(
        registry,
        WorkspaceId("workspace"),
        ModelId("model"),
        ModelVersion("1"),
        data,
        ({"x": 12.0, "y": 0.0},),
    )
    assert len(predicted) == 1


def test_registered_inference_rejects_tampered_artifact(tmp_path: Path) -> None:
    registry = _Registry()
    artifacts = LocalArtifactStore(tmp_path / "artifacts")
    train_register_tabular(
        registry,
        artifacts,
        WorkspaceId("workspace"),
        _classification_rows(),
        dataset=AssetRef(AssetId("dataset"), AssetVersion("v1")),
        experiment_id=ExperimentId("experiment"),
        run_id=MLRunId("run"),
        model_id=ModelId("model"),
        model_version=ModelVersion("1"),
        source_revision="git:abc",
        execution_ref="job:1",
        spec=TrainingSpec("classification", "logistic_regression", ("x", "y"), "label", 0.25, 7),
        now="2026-09-13T10:00:00.000000Z",
    )
    with pytest.raises(ValueError, match="digest"):
        predict_registered_tabular(
            registry,
            WorkspaceId("workspace"),
            ModelId("model"),
            ModelVersion("1"),
            b"tampered",
            ({"x": 12.0, "y": 0.0},),
        )
