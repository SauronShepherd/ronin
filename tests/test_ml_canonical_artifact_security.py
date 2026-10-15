from __future__ import annotations

import hashlib
import pickle

import pytest
from studio_core import AssetId, AssetRef, AssetVersion, WorkspaceId
from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.ml import ExperimentId, MLRunId, ModelId, ModelVersion
from studio_ml import (
    TrainingSpec,
    predict_registered_tabular,
    predict_tabular,
    train_register_tabular,
    train_tabular,
)
from studio_storage.artifacts import ArtifactRef

_PICKLE_TRIPWIRE = False


def _tripwire() -> dict[str, object]:
    global _PICKLE_TRIPWIRE
    _PICKLE_TRIPWIRE = True
    return {"schema": "ronin.sklearn.tabular/v2"}


class _ExecutablePickle:
    def __reduce__(self):
        return (_tripwire, ())


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
        if (
            self.model is not None
            and self.model.model_id == model_id
            and self.model.version == version
        ):
            return self.model
        return None


class _CapturingArtifactStore:
    def __init__(self) -> None:
        self.media_type: str | None = None
        self.data: bytes | None = None

    def put_bytes(self, *, role: str, data: bytes, media_type: str | None = None) -> ArtifactRef:
        assert role == "model"
        self.media_type = media_type
        self.data = data
        digest = hashlib.sha256(data).hexdigest()
        return ArtifactRef(
            role,
            "sha256",
            digest,
            media_type,
            len(data),
            f"artifact://sha256/{digest}",
        )

    def get_bytes(self, ref: ArtifactRef) -> bytes:
        del ref
        assert self.data is not None
        return self.data

    def verify(self, ref: ArtifactRef) -> bool:
        del ref
        return self.data is not None


def _artifact(
    *,
    task: str,
    algorithm: str,
    features: list[str],
    parameters: dict[str, object],
) -> bytes:
    return encode_canonical_json(
        {
            "schema": "ronin.sklearn.tabular/v2",
            "task": task,
            "algorithm": algorithm,
            "features": features,
            "target": "label" if task == "classification" else "target",
            "parameters": parameters,
        }
    )


def _classification_rows():
    return tuple(
        {"x": float(index), "y": float(index % 3), "label": "high" if index >= 10 else "low"}
        for index in range(20)
    )


def _regression_rows():
    return tuple(
        {"x": float(index), "y": float(index * 2), "target": float(index * 3 + 1)}
        for index in range(12)
    )


def test_hand_built_linear_artifact_predicts_from_data_only() -> None:
    artifact = _artifact(
        task="regression",
        algorithm="linear_regression",
        features=["x", "y"],
        parameters={"coefficients": [2.0, -1.0], "intercept": 0.5},
    )
    assert predict_tabular(
        artifact,
        ({"x": 3.0, "y": 1.0}, {"x": 1.0, "y": 4.0}),
    ) == pytest.approx((5.5, -1.5))


def test_hand_built_binary_logistic_artifact_uses_decision_score_sign() -> None:
    artifact = _artifact(
        task="classification",
        algorithm="logistic_regression",
        features=["x", "y"],
        parameters={
            "coefficients": [[1.0, -1.0]],
            "intercepts": [0.0],
            "classes": ["low", "high"],
        },
    )
    assert predict_tabular(
        artifact,
        ({"x": 2.0, "y": 0.0}, {"x": 0.0, "y": 2.0}),
    ) == ("high", "low")


def test_hand_built_multiclass_logistic_artifact_uses_maximum_score() -> None:
    artifact = _artifact(
        task="classification",
        algorithm="logistic_regression",
        features=["x", "y"],
        parameters={
            "coefficients": [[2.0, 0.0], [0.0, 2.0], [-1.0, -1.0]],
            "intercepts": [0.0, 0.0, 1.0],
            "classes": ["x-class", "y-class", "other"],
        },
    )
    assert predict_tabular(
        artifact,
        ({"x": 3.0, "y": 0.0}, {"x": 0.0, "y": 3.0}, {"x": -2.0, "y": -2.0}),
    ) == ("x-class", "y-class", "other")


def test_executable_pickle_bytes_are_rejected_without_running_reduce_target() -> None:
    global _PICKLE_TRIPWIRE
    _PICKLE_TRIPWIRE = False
    malicious = pickle.dumps(_ExecutablePickle(), protocol=pickle.HIGHEST_PROTOCOL)

    with pytest.raises(ValueError, match="canonical JSON"):
        predict_tabular(malicious, ({"x": 1.0},))

    assert not _PICKLE_TRIPWIRE


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "schema": "ronin.sklearn.tabular/v1",
                "task": "regression",
                "algorithm": "linear_regression",
                "features": ["x"],
                "target": "target",
                "parameters": {"coefficients": [1.0], "intercept": 0.0},
            },
            "unsupported ML artifact schema",
        ),
        (
            {
                "schema": "ronin.sklearn.tabular/v2",
                "task": "classification",
                "algorithm": "linear_regression",
                "features": ["x"],
                "target": "label",
                "parameters": {"coefficients": [1.0], "intercept": 0.0},
            },
            "incompatible",
        ),
        (
            {
                "schema": "ronin.sklearn.tabular/v2",
                "task": "regression",
                "algorithm": "linear_regression",
                "features": ["x", "x"],
                "target": "target",
                "parameters": {"coefficients": [1.0, 2.0], "intercept": 0.0},
            },
            "unique",
        ),
        (
            {
                "schema": "ronin.sklearn.tabular/v2",
                "task": "regression",
                "algorithm": "linear_regression",
                "features": ["x", "y"],
                "target": "target",
                "parameters": {"coefficients": [1.0], "intercept": 0.0},
            },
            "coefficient shape",
        ),
    ],
)
def test_invalid_v2_artifact_shapes_fail_closed(payload: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        predict_tabular(encode_canonical_json(payload), ({"x": 1.0, "y": 2.0},))


def test_non_finite_artifact_number_is_rejected_by_canonical_parser() -> None:
    artifact = (
        b'{"algorithm":"linear_regression","features":["x"],'
        b'"parameters":{"coefficients":[NaN],"intercept":0.0},'
        b'"schema":"ronin.sklearn.tabular/v2","target":"target","task":"regression"}'
    )
    with pytest.raises(ValueError, match="canonical JSON"):
        predict_tabular(artifact, ({"x": 1.0},))


def test_expected_feature_signature_mismatch_fails_before_prediction() -> None:
    artifact = _artifact(
        task="regression",
        algorithm="linear_regression",
        features=["x"],
        parameters={"coefficients": [1.0], "intercept": 0.0},
    )
    with pytest.raises(ValueError, match="feature signature"):
        predict_tabular(artifact, ({"x": 1.0},), expected_features=("different",))


def test_trained_artifacts_are_canonical_v2_data() -> None:
    pytest.importorskip("sklearn")
    classification = train_tabular(
        _classification_rows(),
        TrainingSpec("classification", "logistic_regression", ("x", "y"), "label", 0.25, 7),
    )
    regression = train_tabular(
        _regression_rows(),
        TrainingSpec("regression", "linear_regression", ("x", "y"), "target", 0.25, 7),
    )

    for trained in (classification, regression):
        payload = decode_canonical_json(trained.artifact_bytes)
        assert isinstance(payload, dict)
        assert payload["schema"] == "ronin.sklearn.tabular/v2"
        assert set(payload) == {"schema", "task", "algorithm", "features", "target", "parameters"}
        assert isinstance(payload["parameters"], dict)


def test_training_service_uses_json_media_type() -> None:
    pytest.importorskip("sklearn")
    registry = _Registry()
    artifacts = _CapturingArtifactStore()
    model = train_register_tabular(
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
        now="2026-09-14T04:10:00.000000Z",
    )
    assert model == registry.model
    assert artifacts.media_type == "application/vnd.ronin.sklearn-tabular+json"
    assert artifacts.data is not None
    assert decode_canonical_json(artifacts.data)["schema"] == "ronin.sklearn.tabular/v2"


def test_registered_digest_mismatch_still_fails_before_artifact_parse() -> None:
    pytest.importorskip("sklearn")
    registry = _Registry()
    artifacts = _CapturingArtifactStore()
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
        now="2026-09-14T04:10:00.000000Z",
    )

    with pytest.raises(ValueError, match="digest"):
        predict_registered_tabular(
            registry,
            WorkspaceId("workspace"),
            ModelId("model"),
            ModelVersion("1"),
            b"not-json-and-wrong-digest",
            ({"x": 1.0, "y": 1.0},),
        )
