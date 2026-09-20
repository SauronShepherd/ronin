"""Executable tabular ML runtime for Ronin Public v1.

The scikit-learn adapter is optional and deliberately bounded to deterministic
numeric-feature classification/regression baselines. Model artifacts contain only
canonical JSON data required for prediction; no executable model objects are loaded.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from math import ceil, isfinite, sqrt
from typing import Any, Literal, TypeAlias, cast

from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.canonical_json import encode as encode_canonical_json

TaskKind: TypeAlias = Literal["classification", "regression"]
Algorithm: TypeAlias = Literal[
    "logistic_regression",
    "linear_regression",
    "decision_tree_classifier",
    "decision_tree_regressor",
    "random_forest_classifier",
    "random_forest_regressor",
]
ClassificationLabel: TypeAlias = bool | int | float | str

_ARTIFACT_SCHEMA = "ronin.sklearn.tabular/v2"


class MLDependencyError(RuntimeError):
    """Raised when optional ML runtime dependencies are unavailable."""


def _sklearn() -> dict[str, Any]:
    try:
        from sklearn.ensemble import (  # type: ignore[import-untyped]
            GradientBoostingClassifier,
            GradientBoostingRegressor,
            RandomForestClassifier,
            RandomForestRegressor,
        )
        from sklearn.linear_model import (  # type: ignore[import-untyped]
            LinearRegression,
            LogisticRegression,
        )
        from sklearn.metrics import (  # type: ignore[import-untyped]
            accuracy_score,
            mean_absolute_error,
            mean_squared_error,
            r2_score,
        )
        from sklearn.model_selection import train_test_split  # type: ignore[import-untyped]
        from sklearn.tree import (  # type: ignore[import-untyped]
            DecisionTreeClassifier,
            DecisionTreeRegressor,
        )
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise MLDependencyError(
            "tabular ML support requires the optional Ronin ml dependencies"
        ) from exc
    return {
        "LinearRegression": LinearRegression,
        "LogisticRegression": LogisticRegression,
        "DecisionTreeClassifier": DecisionTreeClassifier,
        "DecisionTreeRegressor": DecisionTreeRegressor,
        "RandomForestClassifier": RandomForestClassifier,
        "RandomForestRegressor": RandomForestRegressor,
        "GradientBoostingRegressor": GradientBoostingRegressor,
        "GradientBoostingClassifier": GradientBoostingClassifier,
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


def _finite_float(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _classification_label(value: object) -> ClassificationLabel:
    item = value.item() if hasattr(value, "item") else value
    if isinstance(item, bool):
        return item
    if isinstance(item, int):
        return item
    if isinstance(item, float):
        if not isfinite(item):
            raise ValueError("classification target values must be finite")
        return item
    if isinstance(item, str):
        return _text(item, "classification target")
    raise ValueError("classification target values must be bool, int, float, or string")


@dataclass(frozen=True, slots=True)
class TrainingSpec:
    task: TaskKind
    algorithm: Algorithm
    features: tuple[str, ...]
    target: str
    test_fraction: float = 0.2
    random_seed: int = 17
    parameters: tuple[tuple[str, float | int], ...] = ()

    def __post_init__(self) -> None:
        if self.task not in {"classification", "regression"}:
            raise ValueError("unsupported ML task")
        allowed = {
            "classification": {
                "logistic_regression", "decision_tree_classifier", "random_forest_classifier",
                "gradient_boosting_classifier",
            },
            "regression": {
                "linear_regression", "decision_tree_regressor", "random_forest_regressor",
                "gradient_boosting_regressor", "gradient_boosting_classifier",
            },
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
        if len({name for name, _ in self.parameters}) != len(self.parameters):
            raise ValueError("ML parameters must be unique")
        if any(
            not _text(name, "ML parameter")
            or not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not isfinite(float(value))
            for name, value in self.parameters
        ):
            raise ValueError("ML parameters must be finite numbers")
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
            vector.append(_finite_float(row[name], f"ML feature {name!r}"))
        target = row[spec.target]
        if target is None:
            raise ValueError("ML target values must not be null")
        if spec.task == "regression":
            target = _finite_float(target, "regression target")
        else:
            target = _classification_label(target)
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
                "regression evaluation requires at least two test rows for the mandatory R2 "
                "metric; "
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


def _model_parameters(model: object, spec: TrainingSpec) -> dict[str, object]:
    if spec.algorithm in {"random_forest_classifier", "random_forest_regressor"}:
        estimators = getattr(model, "estimators_", None)
        if not estimators:
            raise ValueError("trained random forest is missing estimators")
        trees = [
                _model_parameters(
                    tree,
                    replace(
                        spec,
                        algorithm=(
                            "decision_tree_classifier"
                            if spec.task == "classification"
                            else "decision_tree_regressor"
                        ),
                    ),
                )
                for tree in estimators
            ]
        if spec.task == "classification":
            classes = [_classification_label(value) for value in model.classes_.tolist()]
            for tree in trees:
                tree["classes"] = classes
        return {
            "trees": trees,
            "hyperparameters": dict(spec.parameters),
        }
    if spec.algorithm == "gradient_boosting_regressor":
        estimators = getattr(model, "estimators_", None)
        init = getattr(model, "init_", None)
        if estimators is None or init is None:
            raise ValueError("trained gradient boosting model is incomplete")
        trees = [
            _model_parameters(
                tree[0], replace(spec, task="regression", algorithm="decision_tree_regressor")
            )
            for tree in estimators
        ]
        return {
            "trees": trees,
            "learning_rate": _finite_float(model.learning_rate, "learning rate"),
            "initial": _finite_float(init.constant_.ravel()[0], "initial prediction"),
            "hyperparameters": dict(spec.parameters),
        }
    if spec.algorithm == "gradient_boosting_classifier":
        estimators = getattr(model, "estimators_", None)
        init = getattr(model, "init_", None)
        classes = getattr(model, "classes_", [])
        if estimators is None or init is None or len(classes) < 2:
            raise ValueError("gradient boosting classifier has invalid fitted state")
        trees = [
            [
                _model_parameters(
                    tree,
                    replace(spec, task="regression", algorithm="decision_tree_regressor"),
                )
                for tree in stage
            ]
            for stage in estimators
        ]
        import numpy as np
        zero = np.zeros((1, len(spec.features)))
        initial = (
            model.decision_function(zero)[0].tolist()
            if len(classes) > 2
            else [float(model.decision_function(zero)[0])]
        )
        return {
            "trees": trees,
            "learning_rate": _finite_float(model.learning_rate, "learning rate"),
            "initial": initial,
            "classes": [_classification_label(value) for value in classes.tolist()],
            "hyperparameters": dict(spec.parameters),
        }
    if spec.algorithm in {"decision_tree_classifier", "decision_tree_regressor"}:
        tree = getattr(model, "tree_", None)
        if tree is None:
            raise ValueError("trained decision tree is missing tree parameters")
        return {
            "children_left": [int(value) for value in tree.children_left.tolist()],
            "children_right": [int(value) for value in tree.children_right.tolist()],
            "features": [int(value) for value in tree.feature.tolist()],
            "thresholds": [
                _finite_float(value, "tree threshold") for value in tree.threshold.tolist()
            ],
            "values": [
                [_finite_float(value, "tree value") for value in row.flatten().tolist()]
                for row in tree.value
            ],
            "classes": (
                [_classification_label(value) for value in getattr(model, "classes_", []).tolist()]
                if spec.task == "classification"
                else []
            ),
            "hyperparameters": dict(spec.parameters),
        }
    if spec.algorithm == "linear_regression":
        coefficients_raw = getattr(model, "coef_", None)
        intercept_raw = getattr(model, "intercept_", None)
        if coefficients_raw is None or intercept_raw is None:
            raise ValueError("trained linear regression model is missing fitted parameters")
        coefficients = [
            _finite_float(value, "linear coefficient") for value in coefficients_raw.tolist()
        ]
        return {
            "coefficients": coefficients,
            "intercept": _finite_float(
                intercept_raw.item() if hasattr(intercept_raw, "item") else intercept_raw,
                "linear intercept",
            ),
            "hyperparameters": dict(spec.parameters),
        }

    coefficients_raw = getattr(model, "coef_", None)
    intercepts_raw = getattr(model, "intercept_", None)
    classes_raw = getattr(model, "classes_", None)
    if coefficients_raw is None or intercepts_raw is None or classes_raw is None:
        raise ValueError("trained logistic regression model is missing fitted parameters")
    logistic_coefficients: list[list[float]] = [
        [_finite_float(value, "logistic coefficient") for value in row]
        for row in coefficients_raw.tolist()
    ]
    intercepts = [_finite_float(value, "logistic intercept") for value in intercepts_raw.tolist()]
    classes = [_classification_label(value) for value in classes_raw.tolist()]
    return {
        "coefficients": logistic_coefficients,
        "intercepts": intercepts,
        "classes": classes,
        "hyperparameters": dict(spec.parameters),
    }


def train_tabular(
    rows: Sequence[Mapping[str, object]],
    spec: TrainingSpec,
) -> TrainedTabularModel:
    """Fit one deterministic baseline and return a non-executable canonical artifact."""

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
        options = dict(spec.parameters)
        model = sk["LogisticRegression"](
            C=float(options.get("C", 1.0)),
            max_iter=int(options.get("max_iter", 1000)),
            random_state=spec.random_seed,
        )
    elif spec.algorithm == "linear_regression":
        model = sk["LinearRegression"]()
    elif spec.algorithm == "decision_tree_classifier":
        model = sk["DecisionTreeClassifier"](
            max_depth=int(dict(spec.parameters).get("max_depth", 5)),
            random_state=spec.random_seed,
        )
    elif spec.algorithm == "decision_tree_regressor":
        model = sk["DecisionTreeRegressor"](
            max_depth=int(dict(spec.parameters).get("max_depth", 5)),
            random_state=spec.random_seed,
        )
    elif spec.algorithm == "random_forest_classifier":
        model = sk["RandomForestClassifier"](
            n_estimators=int(dict(spec.parameters).get("n_estimators", 10)),
            max_depth=int(dict(spec.parameters).get("max_depth", 5)),
            random_state=spec.random_seed,
        )
    elif spec.algorithm == "random_forest_regressor":
        model = sk["RandomForestRegressor"](
            n_estimators=int(dict(spec.parameters).get("n_estimators", 10)),
            max_depth=int(dict(spec.parameters).get("max_depth", 5)),
            random_state=spec.random_seed,
        )
    elif spec.algorithm == "gradient_boosting_classifier":
        options = dict(spec.parameters)
        model = sk["GradientBoostingClassifier"](
            n_estimators=int(options.get("n_estimators", 20)),
            learning_rate=float(options.get("learning_rate", 0.1)),
            max_depth=int(options.get("max_depth", 3)),
            random_state=spec.random_seed,
        )
    else:
        options = dict(spec.parameters)
        model = sk["GradientBoostingRegressor"](
            n_estimators=int(options.get("n_estimators", 20)),
            learning_rate=float(options.get("learning_rate", 0.1)),
            max_depth=int(options.get("max_depth", 3)),
            random_state=spec.random_seed,
        )
    model.fit(x_train, y_train)
    predicted = model.predict(x_test)
    metrics: tuple[tuple[str, float], ...]
    if spec.task == "classification":
        metrics = (("accuracy", float(sk["accuracy_score"](y_test, predicted))),)
    else:
        mse = float(sk["mean_squared_error"](y_test, predicted))
        metrics = (
            ("mae", float(sk["mean_absolute_error"](y_test, predicted))),
            ("r2", float(sk["r2_score"](y_test, predicted))),
            ("rmse", sqrt(mse)),
        )
    artifact = encode_canonical_json(
        {
            "schema": _ARTIFACT_SCHEMA,
            "task": spec.task,
            "algorithm": spec.algorithm,
            "features": list(spec.features),
            "target": spec.target,
            "parameters": _model_parameters(model, spec),
        }
    )
    return TrainedTabularModel(
        spec.task,
        spec.algorithm,
        spec.features,
        spec.target,
        artifact,
        metrics,
    )


def _artifact_payload(artifact_bytes: bytes) -> dict[str, object]:
    try:
        decoded = decode_canonical_json(artifact_bytes)
    except (TypeError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("ML artifact is not valid canonical JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError("ML artifact must be a JSON object")
    required = {"schema", "task", "algorithm", "features", "target", "parameters"}
    if set(decoded) != required:
        raise ValueError("ML artifact fields do not match the supported schema")
    if decoded["schema"] != _ARTIFACT_SCHEMA:
        raise ValueError("unsupported ML artifact schema")
    task = decoded["task"]
    algorithm = decoded["algorithm"]
    if task not in {"classification", "regression"}:
        raise ValueError("ML artifact has invalid task")
    if algorithm not in {
        "logistic_regression",
        "linear_regression",
        "decision_tree_classifier",
        "decision_tree_regressor",
        "random_forest_classifier",
        "random_forest_regressor",
        "gradient_boosting_regressor",
        "gradient_boosting_classifier",
    }:
        raise ValueError("ML artifact has invalid algorithm")
    if (task, algorithm) not in {
        ("classification", "logistic_regression"),
        ("regression", "linear_regression"),
        ("classification", "decision_tree_classifier"),
        ("regression", "decision_tree_regressor"),
        ("classification", "random_forest_classifier"),
        ("regression", "random_forest_regressor"),
        ("regression", "gradient_boosting_regressor"),
        ("classification", "gradient_boosting_classifier"),
    }:
        raise ValueError("ML artifact task and algorithm are incompatible")
    features_raw = decoded["features"]
    if (
        not isinstance(features_raw, list)
        or not features_raw
        or not all(isinstance(item, str) for item in features_raw)
    ):
        raise ValueError("ML artifact has invalid feature metadata")
    features = tuple(_text(cast(str, item), "ML artifact feature") for item in features_raw)
    if len(features) != len(set(features)):
        raise ValueError("ML artifact feature names must be unique")
    target = decoded["target"]
    if not isinstance(target, str):
        raise ValueError("ML artifact target must be a string")
    _text(target, "ML artifact target")
    parameters = decoded["parameters"]
    if not isinstance(parameters, dict):
        raise ValueError("ML artifact parameters must be an object")
    return cast(dict[str, object], decoded)


def _prediction_matrix(
    rows: Sequence[Mapping[str, object]],
    features: tuple[str, ...],
) -> list[list[float]]:
    matrix: list[list[float]] = []
    for index, row in enumerate(rows):
        vector: list[float] = []
        for name in features:
            if name not in row:
                raise ValueError(f"prediction row {index} is missing feature {name!r}")
            vector.append(_finite_float(row[name], f"prediction feature {name!r}"))
        matrix.append(vector)
    return matrix


def _dot(coefficients: Sequence[float], vector: Sequence[float], intercept: float) -> float:
    return (
        sum(coefficient * value for coefficient, value in zip(coefficients, vector, strict=True))
        + intercept
    )


def _linear_predictions(
    parameters: Mapping[str, object], matrix: Sequence[Sequence[float]], feature_count: int
) -> tuple[float, ...]:
    if set(parameters) != {"coefficients", "intercept"}:
        raise ValueError("linear regression artifact parameters are invalid")
    coefficients_raw = parameters["coefficients"]
    if not isinstance(coefficients_raw, list) or len(coefficients_raw) != feature_count:
        raise ValueError("linear regression coefficient shape is invalid")
    coefficients = tuple(_finite_float(value, "linear coefficient") for value in coefficients_raw)
    intercept = _finite_float(parameters["intercept"], "linear intercept")
    return tuple(_dot(coefficients, vector, intercept) for vector in matrix)


def _logistic_predictions(
    parameters: Mapping[str, object],
    matrix: Sequence[Sequence[float]],
    feature_count: int,
) -> tuple[ClassificationLabel, ...]:
    if not {"coefficients", "intercepts", "classes"} <= set(parameters):
        raise ValueError("logistic regression artifact parameters are invalid")
    coefficients_raw = parameters["coefficients"]
    intercepts_raw = parameters["intercepts"]
    classes_raw = parameters["classes"]
    if not isinstance(coefficients_raw, list) or not coefficients_raw:
        raise ValueError("logistic regression coefficients are invalid")
    if not isinstance(intercepts_raw, list) or not isinstance(classes_raw, list):
        raise ValueError("logistic regression intercept/class metadata is invalid")
    coefficients: list[tuple[float, ...]] = []
    for row in coefficients_raw:
        if not isinstance(row, list) or len(row) != feature_count:
            raise ValueError("logistic regression coefficient shape is invalid")
        coefficients.append(tuple(_finite_float(value, "logistic coefficient") for value in row))
    intercepts = tuple(_finite_float(value, "logistic intercept") for value in intercepts_raw)
    classes = tuple(_classification_label(value) for value in classes_raw)
    if len(classes) < 2:
        raise ValueError("logistic regression artifact requires at least two classes")
    if len(classes) == 2:
        if len(coefficients) != 1 or len(intercepts) != 1:
            raise ValueError("binary logistic regression parameter shape is invalid")
        return tuple(
            classes[1] if _dot(coefficients[0], vector, intercepts[0]) > 0 else classes[0]
            for vector in matrix
        )
    if len(coefficients) != len(classes) or len(intercepts) != len(classes):
        raise ValueError("multiclass logistic regression parameter shape is invalid")
    result: list[ClassificationLabel] = []
    for vector in matrix:
        scores = tuple(
            _dot(coefficients[index], vector, intercepts[index]) for index in range(len(classes))
        )
        best = max(range(len(scores)), key=scores.__getitem__)
        result.append(classes[best])
    return tuple(result)


def predict_tabular(
    artifact_bytes: bytes,
    rows: Sequence[Mapping[str, object]],
    *,
    expected_features: tuple[str, ...] | None = None,
    max_rows: int = 100_000,
) -> tuple[object, ...]:
    """Predict from a validated, non-executable canonical model artifact."""

    if max_rows < 1 or max_rows > 1_000_000:
        raise ValueError("ML prediction max_rows must be between 1 and 1000000")
    if len(rows) > max_rows:
        raise ValueError("ML prediction input exceeds configured row limit")
    payload = _artifact_payload(artifact_bytes)
    features = tuple(cast(list[str], payload["features"]))
    if expected_features is not None and features != expected_features:
        raise ValueError("ML artifact feature signature does not match registered model")
    matrix = _prediction_matrix(rows, features)
    parameters = cast(Mapping[str, object], payload["parameters"])
    if payload["algorithm"] == "linear_regression":
        return _linear_predictions(parameters, matrix, len(features))
    if payload["algorithm"] == "gradient_boosting_classifier":
        initial = parameters["initial"]
        class_count = len(cast(list[object], parameters["classes"]))
        totals = [[float(initial)] * len(rows) for initial in cast(list[float], initial)]
        for stage in cast(list[list[dict[str, object]]], parameters["trees"]):
            for class_index, tree in enumerate(stage):
                tree_artifact = encode_canonical_json({
                    "schema": _ARTIFACT_SCHEMA, "task": "regression",
                    "algorithm": "decision_tree_regressor", "features": payload["features"],
                    "target": payload["target"], "parameters": tree,
                })
                values = predict_tabular(
                    tree_artifact, rows, expected_features=features, max_rows=max_rows
                )
                for index, value in enumerate(values):
                    totals[class_index][index] += float(parameters["learning_rate"]) * float(value)
        classes = cast(list[ClassificationLabel], parameters["classes"])
        if class_count == 2:
            import math
            return tuple(
                classes[1] if 1.0 / (1.0 + math.exp(-totals[0][i])) >= 0.5 else classes[0]
                for i in range(len(rows))
            )
        return tuple(
            classes[max(range(class_count), key=lambda c: totals[c][i])]
            for i in range(len(rows))
        )
    if payload["algorithm"] == "gradient_boosting_regressor":
        base = float(parameters["initial"])
        learning_rate = float(parameters["learning_rate"])
        total = [base] * len(rows)
        for tree in cast(list[dict[str, object]], parameters["trees"]):
            tree_artifact = encode_canonical_json({
                "schema": _ARTIFACT_SCHEMA, "task": "regression",
                "algorithm": "decision_tree_regressor", "features": payload["features"],
                "target": payload["target"], "parameters": tree,
            })
            values = predict_tabular(
                tree_artifact, rows, expected_features=features, max_rows=max_rows
            )
            for index, value in enumerate(values):
                total[index] += learning_rate * float(value)
        return tuple(total)
    if payload["algorithm"] in {"random_forest_classifier", "random_forest_regressor"}:
        tree_predictions = [
            predict_tabular(
                encode_canonical_json({
                    "schema": _ARTIFACT_SCHEMA,
                    "task": payload["task"],
                    "algorithm": (
                        "decision_tree_classifier"
                        if payload["task"] == "classification"
                        else "decision_tree_regressor"
                    ),
                    "features": payload["features"],
                    "target": payload["target"],
                    "parameters": tree,
                }), rows, expected_features=features, max_rows=max_rows,
            )
            for tree in cast(list[dict[str, object]], parameters["trees"])
        ]
        if payload["task"] == "regression":
            return tuple(
                sum(float(values[index]) for values in tree_predictions) / len(tree_predictions)
                for index in range(len(rows))
            )
        return tuple(
            max(
                {predictions[index] for predictions in tree_predictions},
                key=lambda value: sum(
                    predictions[index] == value for predictions in tree_predictions
                ),
            )
            for index in range(len(rows))
        )
    if payload["algorithm"] in {"decision_tree_classifier", "decision_tree_regressor"}:
        left = cast(list[int], parameters["children_left"])
        right = cast(list[int], parameters["children_right"])
        node_features = cast(list[int], parameters["features"])
        thresholds = cast(list[float], parameters["thresholds"])
        values = cast(list[list[float]], parameters["values"])
        classes = cast(list[ClassificationLabel], parameters["classes"])
        results: list[object] = []
        for vector in matrix:
            node = 0
            while left[node] != -1:
                node = (
                    left[node]
                    if vector[node_features[node]] <= thresholds[node]
                    else right[node]
                )
            leaf = values[node]
            results.append(
                leaf[0]
                if payload["task"] == "regression"
                else classes[max(range(len(leaf)), key=leaf.__getitem__)]
            )
        return tuple(results)
    return _logistic_predictions(parameters, matrix, len(features))


__all__ = (
    "Algorithm",
    "MLDependencyError",
    "TaskKind",
    "TrainedTabularModel",
    "TrainingSpec",
    "predict_tabular",
    "train_tabular",
)
