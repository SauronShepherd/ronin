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


def _regression_rows(count: int):
    return tuple(
        {"x": float(index), "target": float(index * 2 + 1)}
        for index in range(count)
    )


def test_classification_training_and_prediction() -> None:
    trained = train_tabular(
        _classification_rows(),
        TrainingSpec("classification", "logistic_regression", ("x", "y"), "label", 0.25, 7),
    )
    assert dict(trained.metrics)["accuracy"] >= 0.0
    predicted = predict_tabular(trained.artifact_bytes, ({"x": 2.0, "y": 2.0},))
    assert len(predicted) == 1


@pytest.mark.parametrize("row_count", (4, 5))
def test_regression_rejects_test_partition_too_small_for_r2(row_count: int) -> None:
    with pytest.raises(ValueError, match="at least two test rows"):
        train_tabular(
            _regression_rows(row_count),
            TrainingSpec("regression", "linear_regression", ("x",), "target", 0.2, 7),
        )


@pytest.mark.parametrize("row_count", (4, 5))
def test_binary_classification_rejects_test_partition_smaller_than_class_count(
    row_count: int,
) -> None:
    rows = tuple(
        {
            "x": float(index),
            "label": "low" if index < (row_count + 1) // 2 else "high",
        }
        for index in range(row_count)
    )
    with pytest.raises(ValueError, match="test split must contain at least one row per target class"):
        train_tabular(
            rows,
            TrainingSpec("classification", "logistic_regression", ("x",), "label", 0.2, 7),
        )


def test_classification_rejects_singleton_minority_class() -> None:
    rows = (
        {"x": 0.0, "label": "majority"},
        {"x": 1.0, "label": "majority"},
        {"x": 2.0, "label": "majority"},
        {"x": 3.0, "label": "minority"},
    )
    with pytest.raises(ValueError, match="at least two rows in every target class"):
        train_tabular(
            rows,
            TrainingSpec("classification", "logistic_regression", ("x",), "label", 0.4, 7),
        )


def test_classification_rejects_very_small_test_fraction() -> None:
    with pytest.raises(ValueError, match="test split must contain at least one row per target class"):
        train_tabular(
            _classification_rows(),
            TrainingSpec("classification", "logistic_regression", ("x", "y"), "label", 0.01, 7),
        )


def test_nearby_regression_split_remains_feasible() -> None:
    trained = train_tabular(
        _regression_rows(6),
        TrainingSpec("regression", "linear_regression", ("x",), "target", 0.34, 7),
    )
    assert set(dict(trained.metrics)) == {"mae", "r2", "rmse"}


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
