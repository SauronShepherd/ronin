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
from statistics import median
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
    "gradient_boosting_classifier",
    "gradient_boosting_regressor",
]
Preprocessor: TypeAlias = Literal[
    "identity", "standard_scale", "one_hot", "median_impute", "one_hot_median_impute"
]
ClassificationLabel: TypeAlias = bool | int | float | str

_ARTIFACT_SCHEMA = "ronin.sklearn.tabular/v3"
_PREVIOUS_ARTIFACT_SCHEMA = "ronin.sklearn.tabular/v2"
_MAX_ONE_HOT_CATEGORIES = 256
_MAX_PREPROCESSED_FEATURES = 4096
_MAX_CATEGORY_CHARS = 1024

ALGORITHM_CAPABILITIES: dict[str, frozenset[str]] = {
    "logistic_regression": frozenset({"classification"}),
    "linear_regression": frozenset({"regression"}),
    "decision_tree_classifier": frozenset({"classification"}),
    "decision_tree_regressor": frozenset({"regression"}),
    "random_forest_classifier": frozenset({"classification"}),
    "random_forest_regressor": frozenset({"regression"}),
    "gradient_boosting_classifier": frozenset({"classification"}),
    "gradient_boosting_regressor": frozenset({"regression"}),
}


def algorithm_capabilities() -> dict[str, frozenset[str]]:
    """Return the immutable task matrix exposed by the local ML provider."""

    return dict(ALGORITHM_CAPABILITIES)


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
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return isfinite(float(value))
    except OverflowError:
        return False


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
    preprocessor: Preprocessor = "identity"
    categorical_features: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.task not in {"classification", "regression"}:
            raise ValueError("unsupported ML task")
        if self.preprocessor not in {
            "identity",
            "standard_scale",
            "one_hot",
            "median_impute",
            "one_hot_median_impute",
        }:
            raise ValueError("unsupported ML preprocessor")
        categorical_features = tuple(
            _text(item, "categorical feature") for item in self.categorical_features
        )
        if len(set(categorical_features)) != len(categorical_features) or not set(
            categorical_features
        ) <= set(self.features):
            raise ValueError("categorical features must be unique training features")
        if categorical_features and self.preprocessor not in {"one_hot", "one_hot_median_impute"}:
            raise ValueError("categorical features require a one_hot preprocessor")
        if self.preprocessor in {"one_hot", "one_hot_median_impute"} and not categorical_features:
            raise ValueError("one_hot preprocessing requires categorical features")
        if (
            self.algorithm not in ALGORITHM_CAPABILITIES
            or self.task not in ALGORITHM_CAPABILITIES[self.algorithm]
        ):
            raise ValueError("algorithm is incompatible with ML task")
        features = tuple(_text(item, "ML feature") for item in self.features)
        if not features:
            raise ValueError("ML training requires at least one feature")
        if len(features) != len(set(features)):
            raise ValueError("ML feature names must be unique")
        target = _text(self.target, "ML target")
        if target in features:
            raise ValueError("ML target must not also be a feature")
        if (
            not _is_finite_number(self.test_fraction)
            or not 0 < self.test_fraction < 1
        ):
            raise ValueError("test_fraction must be in (0, 1)")
        if self.random_seed < 0:
            raise ValueError("random_seed must be non-negative")
        if len({name for name, _ in self.parameters}) != len(self.parameters):
            raise ValueError("ML parameters must be unique")
        if any(
            not _text(name, "ML parameter")
            or not _is_finite_number(value)
            for name, value in self.parameters
        ):
            raise ValueError("ML parameters must be finite numbers")
        object.__setattr__(self, "features", features)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "categorical_features", categorical_features)


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
) -> tuple[list[list[float | str | None]], list[object]]:
    if len(rows) < 4:
        raise ValueError("ML training requires at least four rows")
    features: list[list[float | str | None]] = []
    targets: list[object] = []
    for index, row in enumerate(rows):
        missing = [name for name in (*spec.features, spec.target) if name not in row]
        if missing:
            raise ValueError(f"row {index} is missing ML fields: {missing}")
        vector: list[float | str | None] = []
        for name in spec.features:
            if name in spec.categorical_features:
                value = row[name]
                if not isinstance(value, str):
                    raise ValueError(f"categorical feature {name!r} must be a string")
                value = _text(value, f"ML categorical feature {name!r}")
                if len(value) > _MAX_CATEGORY_CHARS:
                    raise ValueError("categorical feature value exceeds the size limit")
                vector.append(value)
            else:
                value = row[name]
                if spec.preprocessor in {"median_impute", "one_hot_median_impute"} and (
                    value is None or value == ""
                ):
                    vector.append(None)
                else:
                    vector.append(_finite_float(value, f"ML feature {name!r}"))
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


def _one_hot_matrix(
    rows: Sequence[Sequence[float | str | None]],
    *,
    features: tuple[str, ...],
    categorical_features: tuple[str, ...],
    categories: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[list[list[float]], dict[str, tuple[str, ...]], tuple[str, ...]]:
    vocabularies = dict(categories or {})
    if categories is None:
        for column in categorical_features:
            column_index = features.index(column)
            vocabularies[column] = tuple(sorted({cast(str, row[column_index]) for row in rows}))
    if any(len(values) > _MAX_ONE_HOT_CATEGORIES for values in vocabularies.values()):
        raise ValueError(f"one_hot categories exceed the {_MAX_ONE_HOT_CATEGORIES} value limit")
    expanded_width = len(features) + sum(
        len(vocabularies[column]) - 1 for column in categorical_features
    )
    if expanded_width > _MAX_PREPROCESSED_FEATURES:
        raise ValueError("one_hot output exceeds the configured feature limit")
    encoded: list[list[float]] = []
    for row in rows:
        vector: list[float] = []
        for column, value in zip(features, row, strict=True):
            if column in categorical_features:
                vocabulary = vocabularies[column]
                vector.extend(1.0 if value == category else 0.0 for category in vocabulary)
            else:
                vector.append(_finite_float(value, f"ML feature {column!r}"))
        encoded.append(vector)
    model_features = tuple(
        f"feature_{index}"
        for index in range(
            len(features) + sum(len(vocabularies[column]) - 1 for column in categorical_features)
        )
    )
    return encoded, vocabularies, model_features


def _median_impute_matrix(
    train: Sequence[Sequence[float | None]],
    evaluation: Sequence[Sequence[float | None]],
    *,
    feature_count: int,
) -> tuple[list[list[float]], list[list[float]], list[float]]:
    medians: list[float] = []
    for column in range(feature_count):
        observed = [row[column] for row in train if row[column] is not None]
        if not observed:
            raise ValueError(f"numeric feature {column} has no training values for imputation")
        medians.append(_finite_float(median(cast(list[float], observed)), "imputation median"))

    def transform(rows: Sequence[Sequence[float | None]]) -> list[list[float]]:
        return [
            [
                medians[index] if value is None else _finite_float(value, "imputed feature")
                for index, value in enumerate(row)
            ]
            for row in rows
        ]

    return transform(train), transform(evaluation), medians


def _median_impute_numeric_columns(
    train: Sequence[Sequence[float | str | None]],
    evaluation: Sequence[Sequence[float | str | None]],
    *,
    features: tuple[str, ...],
    categorical_features: tuple[str, ...],
) -> tuple[list[list[float | str]], list[list[float | str]], dict[str, float]]:
    medians: dict[str, float] = {}
    numeric_indices = [
        index for index, name in enumerate(features) if name not in categorical_features
    ]
    for index in numeric_indices:
        feature = features[index]
        observed = [row[index] for row in train if row[index] is not None]
        if not observed:
            raise ValueError(f"numeric feature {feature!r} has no training values for imputation")
        medians[feature] = _finite_float(median(cast(list[float], observed)), "imputation median")

    def transform(rows: Sequence[Sequence[float | str | None]]) -> list[list[float | str]]:
        transformed: list[list[float | str]] = []
        for row in rows:
            vector: list[float | str] = []
            for name, value in zip(features, row, strict=True):
                if name in categorical_features:
                    vector.append(cast(str, value))
                elif value is None:
                    vector.append(medians[name])
                else:
                    vector.append(_finite_float(value, f"ML feature {name!r}"))
            transformed.append(vector)
        return transformed

    return transform(train), transform(evaluation), medians


def _validate_split_feasibility(targets: Sequence[object], spec: TrainingSpec) -> None:
    row_count = len(targets)
    test_count = ceil(row_count * spec.test_fraction)
    train_count = row_count - test_count

    if test_count < 1 or train_count < 1:
        raise ValueError(
            "training split must leave at least one row for both training and evaluation"
        )

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


def _model_parameters(model: Any, spec: TrainingSpec) -> dict[str, object]:
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
        class_values: Any = getattr(model, "classes_", [])
        if estimators is None or init is None or len(class_values) < 2:
            raise ValueError("gradient boosting classifier has invalid fitted state")
        boosting_trees = [
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
            if len(class_values) > 2
            else [float(model.decision_function(zero)[0])]
        )
        return {
            "trees": boosting_trees,
            "learning_rate": _finite_float(model.learning_rate, "learning rate"),
            "initial": initial,
            "classes": [_classification_label(value) for value in class_values.tolist()],
            "hyperparameters": dict(spec.parameters),
        }
    if spec.algorithm in {"decision_tree_classifier", "decision_tree_regressor"}:
        tree_model: Any = getattr(model, "tree_", None)
        if tree_model is None:
            raise ValueError("trained decision tree is missing tree parameters")
        return {
            "children_left": [int(value) for value in tree_model.children_left.tolist()],
            "children_right": [int(value) for value in tree_model.children_right.tolist()],
            "features": [int(value) for value in tree_model.feature.tolist()],
            "thresholds": [
                _finite_float(value, "tree threshold") for value in tree_model.threshold.tolist()
            ],
            "values": [
                [_finite_float(value, "tree value") for value in row.flatten().tolist()]
                for row in tree_model.value
            ],
            "classes": (
                [
                    _classification_label(value)
                    for value in cast(Any, getattr(model, "classes_", [])).tolist()
                ]
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
    preprocessing: dict[str, object] = {"kind": "identity"}
    model_spec = spec
    if spec.preprocessor == "standard_scale":
        import numpy as np

        means = np.asarray(x_train, dtype=float).mean(axis=0)
        scales = np.asarray(x_train, dtype=float).std(axis=0)
        scales[scales == 0] = 1.0
        x_train = ((np.asarray(x_train, dtype=float) - means) / scales).tolist()
        x_test = ((np.asarray(x_test, dtype=float) - means) / scales).tolist()
        preprocessing = {
            "kind": "standard_scale",
            "means": [_finite_float(value, "preprocessor mean") for value in means.tolist()],
            "scales": [_finite_float(value, "preprocessor scale") for value in scales.tolist()],
        }
    elif spec.preprocessor == "one_hot_median_impute":
        x_train, x_test, numeric_medians = _median_impute_numeric_columns(
            cast(Sequence[Sequence[float | str | None]], x_train),
            cast(Sequence[Sequence[float | str | None]], x_test),
            features=spec.features,
            categorical_features=spec.categorical_features,
        )
        x_train, categories, model_features = _one_hot_matrix(
            x_train,
            features=spec.features,
            categorical_features=spec.categorical_features,
        )
        x_test, _, _ = _one_hot_matrix(
            x_test,
            features=spec.features,
            categorical_features=spec.categorical_features,
            categories=categories,
        )
        preprocessing = {
            "kind": "one_hot_median_impute",
            "categories": {column: list(values) for column, values in categories.items()},
            "medians": numeric_medians,
        }
        model_spec = replace(
            spec,
            features=model_features,
            categorical_features=(),
            preprocessor="identity",
        )
    elif spec.preprocessor == "one_hot":
        x_train, categories, model_features = _one_hot_matrix(
            x_train,
            features=spec.features,
            categorical_features=spec.categorical_features,
        )
        x_test, _, _ = _one_hot_matrix(
            x_test,
            features=spec.features,
            categorical_features=spec.categorical_features,
            categories=categories,
        )
        preprocessing = {
            "kind": "one_hot",
            "categories": {column: list(values) for column, values in categories.items()},
        }
        model_spec = replace(
            spec,
            features=model_features,
            categorical_features=(),
            preprocessor="identity",
        )
    elif spec.preprocessor == "median_impute":
        x_train, x_test, medians = _median_impute_matrix(
            cast(Sequence[Sequence[float | None]], x_train),
            cast(Sequence[Sequence[float | None]], x_test),
            feature_count=len(spec.features),
        )
        preprocessing = {"kind": "median_impute", "medians": medians}
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
            "parameters": _model_parameters(model, model_spec),
            "preprocessing": preprocessing,
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
    schema = decoded.get("schema")
    if schema not in {_ARTIFACT_SCHEMA, _PREVIOUS_ARTIFACT_SCHEMA}:
        raise ValueError("unsupported ML artifact schema")
    expected_fields = (
        required | {"preprocessing"}
        if schema == _ARTIFACT_SCHEMA
        else required
        if schema == _PREVIOUS_ARTIFACT_SCHEMA
        else set()
    )
    if not expected_fields or set(decoded) != expected_fields:
        raise ValueError("ML artifact fields do not match the supported schema")
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
    normalized = cast(dict[str, object], decoded)
    if "preprocessing" not in normalized:
        normalized["preprocessing"] = {"kind": "identity"}
    preprocessing = normalized["preprocessing"]
    if not isinstance(preprocessing, dict):
        raise ValueError("ML artifact preprocessing must be an object")
    if preprocessing.get("kind") == "identity":
        if set(preprocessing) != {"kind"}:
            raise ValueError("identity preprocessing has unexpected parameters")
    elif preprocessing.get("kind") == "standard_scale":
        if set(preprocessing) != {"kind", "means", "scales"}:
            raise ValueError("standard scaling parameters have invalid shape")
        means, scales = preprocessing.get("means"), preprocessing.get("scales")
        if (
            not isinstance(means, list)
            or not isinstance(scales, list)
            or len(means) != len(features)
            or len(scales) != len(features)
        ):
            raise ValueError("standard scaling parameters do not match artifact features")
        normalized_scales = [_finite_float(value, "preprocessor scale") for value in scales]
        if any(value <= 0 for value in normalized_scales):
            raise ValueError("preprocessor scales must be positive")
        preprocessing["means"] = [_finite_float(value, "preprocessor mean") for value in means]
        preprocessing["scales"] = normalized_scales
    elif preprocessing.get("kind") == "median_impute":
        if set(preprocessing) != {"kind", "medians"}:
            raise ValueError("median imputation parameters have invalid shape")
        raw_medians = preprocessing.get("medians")
        if not isinstance(raw_medians, list) or len(raw_medians) != len(features):
            raise ValueError("median imputation values must match artifact features")
        preprocessing["medians"] = [
            _finite_float(value, "imputation median") for value in raw_medians
        ]
    elif preprocessing.get("kind") in {"one_hot", "one_hot_median_impute"}:
        kind = preprocessing.get("kind")
        expected_shape = (
            {"kind", "categories", "medians"}
            if kind == "one_hot_median_impute"
            else {"kind", "categories"}
        )
        if set(preprocessing) != expected_shape:
            raise ValueError("one_hot preprocessing has invalid shape")
        raw_categories = preprocessing.get("categories")
        if not isinstance(raw_categories, dict) or not raw_categories:
            raise ValueError("one_hot categories must be a non-empty object")
        categories: dict[str, tuple[str, ...]] = {}
        for column, values in raw_categories.items():
            if column not in features or not isinstance(values, list) or not values:
                raise ValueError("one_hot categories do not match artifact features")
            if not all(isinstance(value, str) for value in values):
                raise ValueError("one_hot category values must be strings")
            vocabulary = tuple(_text(value, "one_hot category") for value in values)
            if any(len(value) > _MAX_CATEGORY_CHARS for value in vocabulary):
                raise ValueError("one_hot category exceeds the size limit")
            if len(vocabulary) > _MAX_ONE_HOT_CATEGORIES:
                raise ValueError(
                    f"one_hot categories exceed the {_MAX_ONE_HOT_CATEGORIES} value limit"
                )
            if vocabulary != tuple(sorted(set(vocabulary))):
                raise ValueError("one_hot categories must be unique and sorted")
            categories[column] = vocabulary
        expanded_width = len(features) + sum(len(values) - 1 for values in categories.values())
        if expanded_width > _MAX_PREPROCESSED_FEATURES:
            raise ValueError("one_hot output exceeds the configured feature limit")
        preprocessing["categories"] = categories
        if kind == "one_hot_median_impute":
            raw_medians = preprocessing.get("medians")
            numeric_features = set(features) - set(categories)
            if not isinstance(raw_medians, dict) or set(raw_medians) != numeric_features:
                raise ValueError("combined preprocessing medians must match numeric features")
            preprocessing["medians"] = {
                name: _finite_float(value, "imputation median")
                for name, value in raw_medians.items()
            }
    else:
        raise ValueError("ML artifact has unsupported preprocessing")
    return normalized


def _prediction_matrix(
    rows: Sequence[Mapping[str, object]],
    features: tuple[str, ...],
    *,
    categories: Mapping[str, tuple[str, ...]] | None = None,
    medians: Sequence[float] | Mapping[str, float] | None = None,
) -> list[list[float]]:
    category_map = categories or {}
    matrix: list[list[float]] = []
    for index, row in enumerate(rows):
        vector: list[float] = []
        for name in features:
            if name not in row:
                raise ValueError(f"prediction row {index} is missing feature {name!r}")
            if name in category_map:
                value = row[name]
                if not isinstance(value, str):
                    raise ValueError(f"categorical prediction feature {name!r} must be a string")
                value = _text(value, f"categorical prediction feature {name!r}")
                if len(value) > _MAX_CATEGORY_CHARS:
                    raise ValueError("categorical prediction value exceeds the size limit")
                vector.extend(1.0 if value == category else 0.0 for category in category_map[name])
            else:
                value = row[name]
                if medians is not None and (value is None or value == ""):
                    median_value = (
                        medians[name]
                        if isinstance(medians, Mapping)
                        else medians[features.index(name)]
                    )
                    vector.append(median_value)
                else:
                    vector.append(_finite_float(value, f"prediction feature {name!r}"))
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
    if not {"coefficients", "intercept"} <= set(parameters) or set(parameters) - {
        "coefficients",
        "intercept",
        "hyperparameters",
    }:
        raise ValueError("linear regression artifact parameters are invalid")
    if "hyperparameters" in parameters and not isinstance(parameters["hyperparameters"], dict):
        raise ValueError("linear regression hyperparameters are invalid")
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
    preprocessing = cast(Mapping[str, object], payload["preprocessing"])
    categories = cast(Mapping[str, tuple[str, ...]], preprocessing.get("categories", {}))
    medians: Sequence[float] | Mapping[str, float] | None
    if preprocessing["kind"] == "median_impute":
        medians = cast(list[float], preprocessing["medians"])
    elif preprocessing["kind"] == "one_hot_median_impute":
        medians = cast(Mapping[str, float], preprocessing["medians"])
    else:
        medians = None
    matrix = _prediction_matrix(rows, features, categories=categories, medians=medians)
    model_features = (
        tuple(f"feature_{index}" for index in range(len(matrix[0])))
        if matrix and preprocessing["kind"] in {"one_hot", "one_hot_median_impute"}
        else features
    )
    model_feature_count = (
        len(model_features)
        if model_features
        else len(features) + sum(len(values) - 1 for values in categories.values())
    )
    if preprocessing["kind"] == "standard_scale":
        means = cast(list[float], preprocessing["means"])
        scales = cast(list[float], preprocessing["scales"])
        matrix = [
            [
                _finite_float((value - mean) / scale, "scaled prediction feature")
                for value, mean, scale in zip(row, means, scales, strict=True)
            ]
            for row in matrix
        ]
    inference_rows: Sequence[Mapping[str, object]] = rows
    if preprocessing["kind"] == "standard_scale":
        inference_rows = tuple(dict(zip(features, vector, strict=True)) for vector in matrix)
    elif preprocessing["kind"] in {"one_hot", "one_hot_median_impute"}:
        inference_rows = tuple(dict(zip(model_features, vector, strict=True)) for vector in matrix)
    parameters = cast(Mapping[str, object], payload["parameters"])

    def numeric(value: object, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"ML artifact {name} must be numeric")
        return float(value)

    if payload["algorithm"] == "linear_regression":
        return _linear_predictions(parameters, matrix, model_feature_count)
    if payload["algorithm"] == "gradient_boosting_classifier":
        initial = parameters["initial"]
        class_count = len(cast(list[object], parameters["classes"]))
        totals = [
            [numeric(value, "initial") for _ in rows] for value in cast(list[object], initial)
        ]
        for stage in cast(list[list[dict[str, object]]], parameters["trees"]):
            for class_index, tree in enumerate(stage):
                tree_artifact = encode_canonical_json(
                    {
                        "schema": _ARTIFACT_SCHEMA,
                        "task": "regression",
                        "algorithm": "decision_tree_regressor",
                        "features": list(model_features),
                        "target": payload["target"],
                        "parameters": tree,
                        "preprocessing": {"kind": "identity"},
                    }
                )
                predicted_values = predict_tabular(
                    tree_artifact,
                    inference_rows,
                    expected_features=model_features,
                    max_rows=max_rows,
                )
                for index, value in enumerate(predicted_values):
                    totals[class_index][index] += numeric(
                        parameters["learning_rate"], "learning_rate"
                    ) * numeric(value, "tree prediction")
        classes = cast(list[ClassificationLabel], parameters["classes"])
        if class_count == 2:
            import math

            return tuple(
                classes[1] if 1.0 / (1.0 + math.exp(-totals[0][i])) >= 0.5 else classes[0]
                for i in range(len(rows))
            )
        return tuple(
            classes[max(range(class_count), key=lambda c: totals[c][i])] for i in range(len(rows))
        )
    if payload["algorithm"] == "gradient_boosting_regressor":
        base = numeric(parameters["initial"], "initial")
        learning_rate = numeric(parameters["learning_rate"], "learning_rate")
        total = [base] * len(rows)
        for tree in cast(list[dict[str, object]], parameters["trees"]):
            tree_artifact = encode_canonical_json(
                {
                    "schema": _ARTIFACT_SCHEMA,
                    "task": "regression",
                    "algorithm": "decision_tree_regressor",
                    "features": list(model_features),
                    "target": payload["target"],
                    "parameters": tree,
                    "preprocessing": {"kind": "identity"},
                }
            )
            predicted_values = predict_tabular(
                tree_artifact,
                inference_rows,
                expected_features=model_features,
                max_rows=max_rows,
            )
            for index, value in enumerate(predicted_values):
                total[index] += learning_rate * numeric(value, "tree prediction")
        return tuple(total)
    if payload["algorithm"] in {"random_forest_classifier", "random_forest_regressor"}:
        tree_predictions = [
            predict_tabular(
                encode_canonical_json(
                    {
                        "schema": _ARTIFACT_SCHEMA,
                        "task": payload["task"],
                        "algorithm": (
                            "decision_tree_classifier"
                            if payload["task"] == "classification"
                            else "decision_tree_regressor"
                        ),
                        "features": list(model_features),
                        "target": payload["target"],
                        "parameters": tree,
                        "preprocessing": {"kind": "identity"},
                    }
                ),
                inference_rows,
                expected_features=model_features,
                max_rows=max_rows,
            )
            for tree in cast(list[dict[str, object]], parameters["trees"])
        ]
        if payload["task"] == "regression":
            return tuple(
                sum(
                    numeric(tree_values[index], "tree prediction")
                    for tree_values in tree_predictions
                )
                / len(tree_predictions)
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
        node_values = cast(list[list[float]], parameters["values"])
        classes = cast(list[ClassificationLabel], parameters["classes"])
        results: list[object] = []
        for vector in matrix:
            node = 0
            while left[node] != -1:
                node = (
                    left[node] if vector[node_features[node]] <= thresholds[node] else right[node]
                )
            leaf = node_values[node]
            results.append(
                leaf[0]
                if payload["task"] == "regression"
                else classes[max(range(len(leaf)), key=leaf.__getitem__)]
            )
        return tuple(results)
    return _logistic_predictions(parameters, matrix, model_feature_count)


__all__ = (
    "Algorithm",
    "MLDependencyError",
    "TaskKind",
    "TrainedTabularModel",
    "TrainingSpec",
    "predict_tabular",
    "ALGORITHM_CAPABILITIES",
    "algorithm_capabilities",
    "train_tabular",
)
