from pathlib import Path
from statistics import median

import pytest
from studio_core import AssetId, AssetRef, AssetVersion, WorkspaceId
from studio_core.ml import ExperimentId, MLRunId, ModelId, ModelVersion
from studio_ml import (
    TrainingSpec,
    algorithm_capabilities,
    predict_registered_tabular,
    predict_tabular,
    train_register_tabular,
    train_tabular,
)
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

    def get_champion_model(self, workspace_id, model_id):
        del workspace_id
        if self.model is not None and self.model.model_id == model_id:
            return self.model
        return None


def _classification_rows():
    return tuple(
        {"x": float(index), "y": float(index % 3), "label": "high" if index >= 10 else "low"}
        for index in range(20)
    )


def _regression_rows(count: int):
    return tuple({"x": float(index), "target": float(index * 2 + 1)} for index in range(count))


def test_classification_training_and_prediction() -> None:
    trained = train_tabular(
        _classification_rows(),
        TrainingSpec("classification", "logistic_regression", ("x", "y"), "label", 0.25, 7),
    )
    assert dict(trained.metrics)["accuracy"] >= 0.0
    predicted = predict_tabular(trained.artifact_bytes, ({"x": 2.0, "y": 2.0},))
    assert len(predicted) == 1
    with pytest.raises(ValueError, match="max_rows"):
        predict_tabular(trained.artifact_bytes, ({"x": 2.0, "y": 2.0},), max_rows=0)


def test_standard_scaler_is_fit_on_training_rows_and_reused_for_prediction() -> None:
    import json

    rows = tuple(
        {"x": float(index * 100), "constant": 5.0, "target": float(index * 3 + 2)}
        for index in range(20)
    )
    trained = train_tabular(
        rows,
        TrainingSpec(
            "regression",
            "linear_regression",
            ("x", "constant"),
            "target",
            0.25,
            7,
            preprocessor="standard_scale",
        ),
    )
    preprocessing = json.loads(trained.artifact_bytes)["preprocessing"]
    assert preprocessing["kind"] == "standard_scale"
    assert len(preprocessing["means"]) == len(preprocessing["scales"]) == 2
    assert preprocessing["scales"][1] == 1.0
    assert preprocessing["means"][0] != pytest.approx(950.0)
    predictions = predict_tabular(
        trained.artifact_bytes,
        ({"x": 1500.0, "constant": 5.0},),
        expected_features=("x", "constant"),
    )
    assert predictions[0] == pytest.approx(47.0)


def test_median_imputation_is_fit_on_training_rows_and_reused_for_inference() -> None:
    import json

    from sklearn.model_selection import train_test_split

    labels = ["yes" if index % 2 else "no" for index in range(20)]
    train_indices, test_indices = train_test_split(
        list(range(20)), test_size=0.25, random_state=7, stratify=labels
    )
    held_out = test_indices[0]
    rows = tuple(
        {
            "x": None if index in {train_indices[0], held_out} else float(index),
            "label": labels[index],
        }
        for index in range(20)
    )
    trained = train_tabular(
        rows,
        TrainingSpec(
            "classification",
            "logistic_regression",
            ("x",),
            "label",
            test_fraction=0.25,
            random_seed=7,
            preprocessor="median_impute",
        ),
    )
    preprocessing = json.loads(trained.artifact_bytes)["preprocessing"]
    expected = median(float(index) for index in train_indices if index != train_indices[0])
    assert preprocessing == {"kind": "median_impute", "medians": [expected]}
    missing_prediction = predict_tabular(trained.artifact_bytes, ({"x": None},))
    blank_prediction = predict_tabular(trained.artifact_bytes, ({"x": ""},))
    explicit_prediction = predict_tabular(trained.artifact_bytes, ({"x": expected},))
    assert missing_prediction == blank_prediction == explicit_prediction


def test_median_imputation_rejects_all_missing_training_feature() -> None:
    from sklearn.model_selection import train_test_split

    labels = [index % 2 for index in range(20)]
    train_indices, test_indices = train_test_split(
        list(range(20)), test_size=0.2, random_state=7, stratify=labels
    )
    test_only = set(test_indices)
    rows = tuple(
        {"x": float(index) if index in test_only else None, "label": index % 2}
        for index in range(20)
    )
    with pytest.raises(ValueError, match="no training values"):
        train_tabular(
            rows,
            TrainingSpec(
                "classification",
                "logistic_regression",
                ("x",),
                "label",
                test_fraction=0.2,
                random_seed=7,
                preprocessor="median_impute",
            ),
        )


@pytest.mark.parametrize("medians", [[], [float("nan")]])
def test_median_imputation_artifact_rejects_invalid_medians(medians: list[float]) -> None:
    import json

    trained = train_tabular(
        _classification_rows(),
        TrainingSpec(
            "classification",
            "logistic_regression",
            ("x", "y"),
            "label",
            preprocessor="median_impute",
        ),
    )
    payload = json.loads(trained.artifact_bytes)
    payload["preprocessing"] = {"kind": "median_impute", "medians": medians}
    with pytest.raises(ValueError, match="canonical JSON|imputation"):
        predict_tabular(json.dumps(payload).encode(), ({"x": 1.0, "y": 1.0},))


def test_standard_scaler_rejects_malformed_artifact_parameters() -> None:
    import json

    trained = train_tabular(
        _regression_rows(20),
        TrainingSpec(
            "regression", "linear_regression", ("x",), "target", preprocessor="standard_scale"
        ),
    )
    payload = json.loads(trained.artifact_bytes)
    payload["preprocessing"]["scales"] = [0.0]
    with pytest.raises(ValueError, match="positive"):
        predict_tabular(json.dumps(payload).encode(), ({"x": 5.0},))


@pytest.mark.parametrize(
    ("task", "algorithm", "rows", "features", "target"),
    [
        (
            "classification",
            "random_forest_classifier",
            _classification_rows(),
            ("x", "y"),
            "label",
        ),
        (
            "regression",
            "gradient_boosting_regressor",
            _regression_rows(20),
            ("x",),
            "target",
        ),
    ],
)
def test_standard_scaler_survives_tree_ensemble_round_trip(
    task, algorithm, rows, features, target
) -> None:
    trained = train_tabular(
        rows,
        TrainingSpec(
            task,
            algorithm,
            features,
            target,
            random_seed=7,
            preprocessor="standard_scale",
        ),
    )
    prediction_rows = tuple({name: row[name] for name in features} for row in rows[:3])
    assert len(predict_tabular(trained.artifact_bytes, prediction_rows)) == 3


def test_one_hot_uses_training_vocabulary_and_unknown_values_map_to_zero() -> None:
    import json

    from sklearn.model_selection import train_test_split

    labels = ["yes" if index % 2 else "no" for index in range(20)]
    train_indices, test_indices = train_test_split(
        list(range(20)), test_size=0.25, random_state=7, stratify=labels
    )
    held_out_only = test_indices[0]
    rows = tuple(
        {
            "segment": "held-out" if index == held_out_only else ("blue" if index % 2 else "red"),
            "age": float(index),
            "label": labels[index],
        }
        for index in range(20)
    )
    trained = train_tabular(
        rows,
        TrainingSpec(
            "classification",
            "logistic_regression",
            ("segment", "age"),
            "label",
            0.25,
            7,
            preprocessor="one_hot",
            categorical_features=("segment",),
        ),
    )
    preprocessing = json.loads(trained.artifact_bytes)["preprocessing"]
    assert preprocessing["categories"]["segment"] == sorted(
        {rows[index]["segment"] for index in train_indices}
    )
    assert "held-out" not in preprocessing["categories"]["segment"]
    predictions = predict_tabular(
        trained.artifact_bytes,
        ({"segment": "unseen", "age": 4.0},),
        expected_features=("segment", "age"),
    )
    assert len(predictions) == 1


def test_combined_preprocessing_fits_numeric_medians_and_categories_on_training_rows() -> None:
    import json

    from sklearn.model_selection import train_test_split

    labels = ["yes" if index % 2 else "no" for index in range(20)]
    train_indices, test_indices = train_test_split(
        list(range(20)), test_size=0.25, random_state=7, stratify=labels
    )
    held_out = test_indices[0]
    missing_training = train_indices[0]
    rows = tuple(
        {
            "segment": "held-out" if index == held_out else ("blue" if index % 2 else "red"),
            "age": None
            if index == missing_training
            else (10000.0 if index == held_out else float(index)),
            "label": labels[index],
        }
        for index in range(20)
    )
    trained = train_tabular(
        rows,
        TrainingSpec(
            "classification",
            "logistic_regression",
            ("segment", "age"),
            "label",
            test_fraction=0.25,
            random_seed=7,
            preprocessor="one_hot_median_impute",
            categorical_features=("segment",),
        ),
    )
    preprocessing = json.loads(trained.artifact_bytes)["preprocessing"]
    expected_median = median(float(index) for index in train_indices if index != missing_training)
    assert preprocessing["categories"] == {"segment": ["blue", "red"]}
    assert preprocessing["medians"] == {"age": expected_median}
    unknown_with_missing = predict_tabular(
        trained.artifact_bytes, ({"segment": "unseen", "age": None},)
    )
    unknown_with_imputed = predict_tabular(
        trained.artifact_bytes, ({"segment": "unseen", "age": expected_median},)
    )
    assert unknown_with_missing == unknown_with_imputed


def test_one_hot_rejects_invalid_or_unsorted_artifact_vocabulary() -> None:
    import json

    rows = tuple(
        {"segment": "blue" if index % 2 else "red", "label": index % 2} for index in range(20)
    )
    trained = train_tabular(
        rows,
        TrainingSpec(
            "classification",
            "logistic_regression",
            ("segment",),
            "label",
            preprocessor="one_hot",
            categorical_features=("segment",),
        ),
    )
    payload = json.loads(trained.artifact_bytes)
    payload["preprocessing"]["categories"]["segment"] = ["red", "blue"]
    with pytest.raises(ValueError, match="unique and sorted"):
        predict_tabular(json.dumps(payload).encode(), ({"segment": "red"},))


def test_one_hot_limits_category_count_and_value_size() -> None:
    from studio_ml.runtime import _one_hot_matrix

    values = [[f"category-{index}"] for index in range(257)]
    with pytest.raises(ValueError, match="256 value limit"):
        _one_hot_matrix(
            values,
            features=("segment",),
            categorical_features=("segment",),
        )
    wide_features = tuple(f"category_{index}" for index in range(17))
    wide_rows = tuple(tuple(f"value-{row}" for _ in wide_features) for row in range(256))
    with pytest.raises(ValueError, match="configured feature limit"):
        _one_hot_matrix(
            wide_rows,
            features=wide_features,
            categorical_features=wide_features,
        )
    with pytest.raises(ValueError, match="size limit"):
        train_tabular(
            tuple({"segment": "x" * 1025, "label": index % 2} for index in range(20)),
            TrainingSpec(
                "classification",
                "logistic_regression",
                ("segment",),
                "label",
                preprocessor="one_hot",
                categorical_features=("segment",),
            ),
        )


@pytest.mark.parametrize("row_count", [4, 5])
def test_regression_rejects_test_partition_too_small_for_r2(row_count: int) -> None:
    with pytest.raises(ValueError, match="at least two test rows"):
        train_tabular(
            _regression_rows(row_count),
            TrainingSpec("regression", "linear_regression", ("x",), "target", 0.2, 7),
        )


@pytest.mark.parametrize("row_count", [4, 5])
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
    with pytest.raises(
        ValueError, match="test split must contain at least one row per target class"
    ):
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
    with pytest.raises(
        ValueError, match="test split must contain at least one row per target class"
    ):
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


def test_regression_accepts_contract_split_fraction_above_one_half() -> None:
    trained = train_tabular(
        _regression_rows(20),
        TrainingSpec("regression", "linear_regression", ("x",), "target", 0.75, 7),
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


def test_champion_inference_loads_artifact_by_registered_reference(tmp_path: Path) -> None:
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
    from studio_ml import predict_champion_tabular

    predicted = predict_champion_tabular(
        registry,
        WorkspaceId("workspace"),
        ModelId("model"),
        ({"x": 12.0, "y": 0.0},),
        load_artifact=lambda reference: (
            tmp_path
            / "artifacts"
            / "sha256"
            / reference.rsplit("/", 1)[-1][:2]
            / reference.rsplit("/", 1)[-1]
        ).read_bytes(),
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


def test_classification_split_rejects_insufficient_test_rows() -> None:
    with pytest.raises(ValueError, match="every target class"):
        train_tabular(
            (
                {"x": 1.0, "label": "a"},
                {"x": 2.0, "label": "b"},
                {"x": 3.0, "label": "c"},
                {"x": 4.0, "label": "a"},
            ),
            TrainingSpec("classification", "logistic_regression", ("x",), "label", 0.2),
        )


def test_algorithm_capability_matrix_rejects_cross_task_selection() -> None:
    capabilities = algorithm_capabilities()
    assert capabilities["gradient_boosting_classifier"] == frozenset({"classification"})
    with pytest.raises(ValueError, match="incompatible"):
        TrainingSpec("regression", "gradient_boosting_classifier", ("x",), "y")
