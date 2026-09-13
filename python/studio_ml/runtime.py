"""Executable tabular ML runtime for Ronin Public v1.

The scikit-learn adapter is optional and deliberately bounded to deterministic
numeric-feature classification/regression baselines. Model artifacts are internal
content-addressed artifacts; this runtime never loads arbitrary external pickle bytes.
"""

from __future__ import annotations

import pickle
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import ceil, sqrt
from typing import Any, Literal, TypeAlias

TaskKind: TypeAlias = Literal["classification", "regression"]
Algorithm: TypeAlias = Literal["logistic_regression", "linear_regression"]


class MLDependencyError(RuntimeError):
    """Raised when optional ML runtime dependencies are unavailable."""


def _sklearn() -> dict[str, Any]:
    try:
        from sklearn.linear_model import LinearRegression, LogisticRegression
        from sklearn.metrics import accuracy_score, mean_absolute_error, mean_squared_error, r2_score
        from sklearn.model_selection import train_test_split
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise MLDependencyError(
            "tabular ML support requires the optional Ronin ml dependencies"
        ) from exc
    return {
        "LinearRegression": LinearRegression,
        "LogisticRegression": LogisticRegression,
        "accuracy_score": accuracy_score,
        "mean_absolute_error": mean_absolute_error,
        "mean_squared_error": mean_squared_error,
        "r2_score": r2_score,
        "train_test_split": train_test_split,
    }


def _text(value: str, name: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    return value


@dataclass(frozen=True, slots=True)
class TrainingSpec:
    task: TaskKind
    algorithm: Algorithm
    features: tuple[str, ...]
    target: str
    test_fraction: float = 0.2
    random_seed: int = 17

    def __post_init__(self) -> None:
        if self.task not in {"classification", "regression"}:
            raise ValueError("unsupported ML task")
        allowed = {
            "classification": {"logistic_regression"},
            "regression": {"linear_regression"},
        }
        if self.algorithm not in allowed[self.task]:
            raise ValueError("algorithm is incompatible with ML task")
        features = tuple(_text(item, "ML feature") for item in self.features)
        if not features:
            raise ValueError("ML training requires at least one feature")
        if len(features) != len(set(features)):
            raise ValueError("ML feature names must be unique")
        target = _text(self.target, "ML target")
        if target in features:
            raise ValueError("ML target must not also be a feature")
        if not 0 < self.test_fraction < 0.5:
            raise ValueError("test_fraction must be in (0, 0.5)")
        if self.random_seed < 0:
            raise ValueError("random_seed must be non-negative")
        object.__setattr__(self, "features", features)
        object.__setattr__(self, "target", target)


@dataclass(frozen=True, slots=True)
class TrainedTabularModel:
    task: TaskKind
    algorithm: Algorithm
    features: tuple[str, ...]
    target: str
    artifact_bytes: bytes
    metrics: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        if not self.artifact_bytes:
            raise ValueError("trained ML artifact must not be empty")
        metrics = tuple(sorted(self.metrics))
        if any(value != value or value in (float("inf"), float("-inf")) for _, value in metrics):
            raise ValueError("ML metrics must be finite")
        object.__setattr__(self, "metrics", metrics)


def _matrix(
    rows: Sequence[Mapping[str, object]],
    spec: TrainingSpec,
) -> tuple[list[list[float]], list[object]]:
    if len(rows) < 4:
        raise ValueError("ML training requires at least four rows")
    features: list[list[float]] = []
    targets: list[object] = []
    for index, row in enumerate(rows):
        missing = [name for name in (*spec.features, spec.target) if name not in row]
        if missing:
            raise ValueError(f"row {index} is missing ML fields: {missing}")
        vector: list[float] = []
        for name in spec.features:
            value = row[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"ML feature {name!r} must be numeric")
            vector.append(float(value))
        target = row[spec.target]
        if target is None:
            raise ValueError("ML target values must not be null")
        if spec.task == "regression" and (
            isinstance(target, bool) or not isinstance(target, (int, float))
        ):
            raise ValueError("regression target must be numeric")
        features.append(vector)
        targets.append(target)
    if spec.task == "classification" and len({repr(value) for value in targets}) < 2:
        raise ValueError("classification training requires at least two target classes")
    return features, targets


def _validate_split_feasibility(targets: Sequence[object], spec: TrainingSpec) -> None:
    row_count = len(targets)
    test_count = ceil(row_count * spec.test_fraction)
    train_count = row_count - test_count

    if spec.task == "regression":
        if test_count < 2:
            raise ValueError(
                "regression evaluation requires at least two test rows for the mandatory R2 metric; "
                "increase the dataset size or test_fraction"
            )
        return

    class_counts = Counter(repr(value) for value in targets)
    class_count = len(class_counts)
    if min(class_counts.values()) < 2:
        raise ValueError(
            "classification stratification requires at least two rows in every target class"
        )
    if train_count < class_count:
        raise ValueError(
            "classification training split must contain at least one row per target class; "
            "increase the dataset size or reduce test_fraction"
        )
    if test_count < class_count:
        raise ValueError(
            "classification test split must contain at least one row per target class; "
            "increase the dataset size or test_fraction"
        )


def train_tabular(
    rows: Sequence[Mapping[str, object]],
    spec: TrainingSpec,
) -> TrainedTabularModel:
    """Fit one deterministic baseline and return a trusted internal artifact."""

    sk = _sklearn()
    x, y = _matrix(rows, spec)
    _validate_split_feasibility(y, spec)
    stratify = y if spec.task == "classification" else None
    x_train, x_test, y_train, y_test = sk["train_test_split"](
        x,
        y,
        test_size=spec.test_fraction,
        random_state=spec.random_seed,
        stratify=stratify,
    )
    if spec.algorithm == "logistic_regression":
        model = sk["LogisticRegression"](max_iter=1000, random_state=spec.random_seed)
    else:
        model = sk["LinearRegression"]()
    model.fit(x_train, y_train)
    predicted = model.predict(x_test)
    if spec.task == "classification":
        metrics = (("accuracy", float(sk["accuracy_score"](y_test, predicted))),)
    else:
        mse = float(sk["mean_squared_error"](y_test, predicted))
        metrics = (
            ("mae", float(sk["mean_absolute_error"](y_test, predicted))),
            ("r2", float(sk["r2_score"](y_test, predicted))),
            ("rmse", sqrt(mse)),
        )
    payload = {
        "schema": "ronin.sklearn.tabular/v1",
        "task": spec.task,
        "algorithm": spec.algorithm,
        "features": spec.features,
        "target": spec.target,
        "model": model,
    }
    artifact = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
    return TrainedTabularModel(
        spec.task,
        spec.algorithm,
        spec.features,
        spec.target,
        artifact,
        metrics,
    )


def predict_tabular(
    artifact_bytes: bytes,
    rows: Sequence[Mapping[str, object]],
    *,
    expected_features: tuple[str, ...] | None = None,
) -> tuple[object, ...]:
    """Predict using a trusted Ronin-created artifact from the configured ArtifactStore."""

    try:
        payload = pickle.loads(artifact_bytes)  # noqa: S301 - trusted internal artifact boundary
    except Exception as exc:
        raise ValueError("ML artifact is not a valid Ronin tabular model") from exc
    if not isinstance(payload, dict) or payload.get("schema") != "ronin.sklearn.tabular/v1":
        raise ValueError("unsupported ML artifact schema")
    features = payload.get("features")
    model = payload.get("model")
    if not isinstance(features, tuple) or not all(isinstance(item, str) for item in features):
        raise ValueError("ML artifact has invalid feature metadata")
    if expected_features is not None and features != expected_features:
        raise ValueError("ML artifact feature signature does not match registered model")
    matrix: list[list[float]] = []
    for index, row in enumerate(rows):
        vector: list[float] = []
        for name in features:
            if name not in row:
                raise ValueError(f"prediction row {index} is missing feature {name!r}")
            value = row[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"prediction feature {name!r} must be numeric")
            vector.append(float(value))
        matrix.append(vector)
    if model is None or not hasattr(model, "predict"):
        raise ValueError("ML artifact does not contain a predictor")
    predicted = model.predict(matrix)
    return tuple(predicted.tolist() if hasattr(predicted, "tolist") else predicted)


__all__ = (
    "Algorithm",
    "MLDependencyError",
    "TaskKind",
    "TrainedTabularModel",
    "TrainingSpec",
    "predict_tabular",
    "train_tabular",
)
