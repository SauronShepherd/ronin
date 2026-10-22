"""Application services and reference in-memory adapter for ML Studio."""
# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any

from studio_core import WorkspaceId

from .domain import (
    PIPELINE_SCHEMA_V2,
    FeatureDefinition,
    Lab,
    NodeKind,
    PipelineIR,
    PipelineNode,
)
from .drift import DriftPolicy
from .ports import FeatureDefinitionStore, MLLabStore
from .quality import QualitySuite, validate_quality_suite


class MLLabConflict(RuntimeError):
    """Raised when an immutable lab identity is reused with different content."""


class FeatureDefinitionConflict(RuntimeError):
    """Raised when a feature identity/version is reused with different content."""


class QualitySuiteConflict(RuntimeError):
    """Raised when a suite version is reused or written out of order."""


class DriftPolicyConflict(RuntimeError):
    """Raised when a drift policy version is reused or written out of order."""


def compile_lab_pipeline(
    lab: Lab,
    *,
    algorithm: str | None = None,
    preprocessor: str = "identity",
    candidate_algorithms: tuple[str, ...] | None = None,
    candidate_cluster_counts: tuple[int, ...] | None = None,
    candidate_preprocessors: tuple[str, ...] | None = None,
    selection_metric: str | None = None,
    selection_direction: str | None = None,
    register_model: tuple[str, str] | None = None,
) -> PipelineIR:
    """Build the deterministic pipeline definition bound to an immutable Lab."""

    parameters = {
        "backend_id": lab.backend_id,
        "lab_digest": lab.digest,
        "seed": str(lab.seed),
        "task": lab.task,
    }
    if register_model is not None and (
        not isinstance(register_model, tuple)
        or len(register_model) != 2
        or any(
            not isinstance(value, str) or not value or value != value.strip()
            for value in register_model
        )
    ):
        raise ValueError("register_model must contain a trimmed model id and version")
    if algorithm is not None:
        from .runtime import ALGORITHM_CAPABILITIES

        if lab.task == "clustering" or lab.task not in ALGORITHM_CAPABILITIES.get(
            algorithm, frozenset()
        ):
            raise ValueError("algorithm is not supported for this Lab task")
        parameters["algorithm"] = algorithm
    if preprocessor not in {
        "identity",
        "standard_scale",
        "one_hot",
        "median_impute",
        "one_hot_median_impute",
    }:
        raise ValueError("preprocessor is not supported for this Lab")
    has_categorical = any(feature.role == "categorical" for feature in lab.features)
    if candidate_preprocessors is not None and preprocessor != "identity":
        raise ValueError("preprocessor cannot be combined with candidate_preprocessors")
    if candidate_preprocessors is None:
        if lab.task == "clustering" and preprocessor != "identity":
            raise ValueError("preprocessor is not supported for clustering Labs")
        if has_categorical and preprocessor not in {"one_hot", "one_hot_median_impute"}:
            if preprocessor == "median_impute":
                raise ValueError("median imputation requires numeric Lab features")
            raise ValueError("categorical Lab features require the one_hot preprocessor")
        if preprocessor in {"one_hot", "one_hot_median_impute"} and not has_categorical:
            raise ValueError("one_hot preprocessing requires categorical Lab features")
    if preprocessor != "identity":
        parameters["preprocessor"] = preprocessor

    if candidate_cluster_counts is not None and (
        candidate_algorithms is not None or candidate_preprocessors is not None
    ):
        raise ValueError("clustering candidates cannot be combined with supervised candidates")
    if candidate_cluster_counts is not None:
        if lab.task != "clustering":
            raise ValueError("candidate_cluster_counts are supported only for clustering Labs")
        if (
            not isinstance(candidate_cluster_counts, tuple)
            or not 2 <= len(candidate_cluster_counts) <= 8
            or any(
                not isinstance(item, int) or isinstance(item, bool) or not 2 <= item <= 32
                for item in candidate_cluster_counts
            )
            or len(set(candidate_cluster_counts)) != len(candidate_cluster_counts)
        ):
            raise ValueError(
                "candidate_cluster_counts must contain 2 to 8 unique counts from 2 to 32"
            )
        metric = selection_metric if selection_metric is not None else "calinski_harabasz"
        direction = selection_direction if selection_direction is not None else "maximize"
        if metric != "calinski_harabasz" or direction != "maximize":
            raise ValueError(
                "clustering candidate selection supports calinski_harabasz with maximize direction"
            )
        nodes = [
            _node("profile"),
            _node("quality_gate", ("profile",)),
            _node("prepare", ("quality_gate",)),
        ]
        cluster_evaluations: list[str] = []
        for index, cluster_count in enumerate(candidate_cluster_counts, start=1):
            train_id = f"train_{index}"
            evaluate_id = f"evaluate_{index}"
            nodes.append(PipelineNode(train_id, "train", ("prepare",), {"clusters": cluster_count}))
            nodes.append(PipelineNode(evaluate_id, "evaluate", (train_id,)))
            cluster_evaluations.append(evaluate_id)
        nodes.append(
            PipelineNode(
                "select",
                "select",
                tuple(cluster_evaluations),
                {"metric": metric, "direction": direction},
            )
        )
        if register_model is not None:
            nodes.append(_registration_node(register_model))
        if len(nodes) > 24:
            raise ValueError("candidate pipeline exceeds the 24-node execution limit")
        return PipelineIR(
            tuple(nodes), parameters=tuple(sorted(parameters.items())), schema=PIPELINE_SCHEMA_V2
        )

    if candidate_preprocessors is not None:
        if lab.task == "clustering":
            raise ValueError("candidate_preprocessors are not supported for clustering Labs")
        if (
            not isinstance(candidate_preprocessors, tuple)
            or not 2 <= len(candidate_preprocessors) <= 5
            or not all(
                isinstance(item, str) and item and item == item.strip()
                for item in candidate_preprocessors
            )
            or len(set(candidate_preprocessors)) != len(candidate_preprocessors)
        ):
            raise ValueError("candidate_preprocessors must contain 2 to 5 unique preprocessors")
        for candidate_preprocessor in candidate_preprocessors:
            if (
                not isinstance(candidate_preprocessor, str)
                or candidate_preprocessor != candidate_preprocessor.strip()
            ):
                raise ValueError("candidate_preprocessor is not supported for this Lab")
            compile_lab_pipeline(lab, algorithm=algorithm, preprocessor=candidate_preprocessor)
        if candidate_algorithms is not None:
            from .runtime import ALGORITHM_CAPABILITIES

            if algorithm is not None:
                raise ValueError("algorithm cannot be combined with candidate_algorithms")
            if (
                not isinstance(candidate_algorithms, tuple)
                or not 2 <= len(candidate_algorithms) <= 8
                or not all(
                    isinstance(item, str)
                    and bool(item)
                    and item == item.strip()
                    and lab.task in ALGORITHM_CAPABILITIES.get(item, frozenset())
                    for item in candidate_algorithms
                )
                or len(set(candidate_algorithms)) != len(candidate_algorithms)
            ):
                raise ValueError("candidate algorithms are not supported for this Lab task")
            if len(candidate_algorithms) * len(candidate_preprocessors) > 8:
                raise ValueError("candidate grid supports at most 8 combinations")
        metric = (
            selection_metric
            if selection_metric is not None
            else ("accuracy" if lab.task == "classification" else "r2")
        )
        supported_metrics = (
            {"accuracy"} if lab.task == "classification" else {"r2", "mean_squared_error"}
        )
        effective_direction = (
            selection_direction
            if selection_direction is not None
            else ("minimize" if metric == "mean_squared_error" else "maximize")
        )
        if (
            not isinstance(metric, str)
            or metric not in supported_metrics
            or not isinstance(effective_direction, str)
            or effective_direction not in {"maximize", "minimize"}
        ):
            raise ValueError("selection metric/direction is not supported for this Lab task")
        nodes = [_node("profile"), _node("quality_gate", ("profile",))]
        prepare_ids: dict[str, str] = {}
        for index, candidate_preprocessor in enumerate(candidate_preprocessors, start=1):
            prepare_id = f"prepare_{index}"
            prepare_ids[candidate_preprocessor] = prepare_id
            nodes.append(
                PipelineNode(
                    prepare_id,
                    "prepare",
                    ("quality_gate",),
                    {"preprocessor": candidate_preprocessor},
                )
            )
        preprocessor_evaluations: list[str] = []
        algorithm_candidates = candidate_algorithms or ((algorithm,) if algorithm else (None,))
        for prep_index, candidate_preprocessor in enumerate(candidate_preprocessors, start=1):
            for algorithm_index, candidate_algorithm in enumerate(algorithm_candidates, start=1):
                suffix = f"{prep_index}_{algorithm_index}"
                train_id = f"train_{suffix}"
                evaluate_id = f"evaluate_{suffix}"
                train_config = {"algorithm": candidate_algorithm} if candidate_algorithm else {}
                nodes.append(
                    PipelineNode(
                        train_id, "train", (prepare_ids[candidate_preprocessor],), train_config
                    )
                )
                nodes.append(PipelineNode(evaluate_id, "evaluate", (train_id,)))
                preprocessor_evaluations.append(evaluate_id)
        nodes.append(
            PipelineNode(
                "select",
                "select",
                tuple(preprocessor_evaluations),
                {"metric": metric, "direction": effective_direction},
            )
        )
        if register_model is not None:
            nodes.append(_registration_node(register_model))
        if len(nodes) > 24:
            raise ValueError("candidate grid exceeds the 24-node execution limit")
        return PipelineIR(
            tuple(nodes), parameters=tuple(sorted(parameters.items())), schema=PIPELINE_SCHEMA_V2
        )

    if candidate_algorithms is not None:
        from .runtime import ALGORITHM_CAPABILITIES

        if algorithm is not None:
            raise ValueError("algorithm cannot be combined with candidate_algorithms")
        if lab.task == "clustering":
            raise ValueError("candidate algorithms are not supported for clustering Labs")
        if not isinstance(candidate_algorithms, tuple) or not 2 <= len(candidate_algorithms) <= 8:
            raise ValueError("candidate_algorithms must contain 2 to 8 unique algorithms")
        if not all(
            isinstance(item, str) and item and item == item.strip() for item in candidate_algorithms
        ):
            raise ValueError("candidate algorithm is not supported for this Lab task")
        if len(set(candidate_algorithms)) != len(candidate_algorithms):
            raise ValueError("candidate_algorithms must contain 2 to 8 unique algorithms")
        if any(
            not isinstance(item, str)
            or not item
            or item != item.strip()
            or lab.task not in ALGORITHM_CAPABILITIES.get(item, frozenset())
            for item in candidate_algorithms
        ):
            raise ValueError("candidate algorithm is not supported for this Lab task")
        metric = (
            selection_metric
            if selection_metric is not None
            else ("accuracy" if lab.task == "classification" else "r2")
        )
        supported_metrics = (
            {"accuracy"} if lab.task == "classification" else {"r2", "mean_squared_error"}
        )
        effective_direction = (
            selection_direction
            if selection_direction is not None
            else ("minimize" if metric == "mean_squared_error" else "maximize")
        )
        if (
            not isinstance(metric, str)
            or metric not in supported_metrics
            or not isinstance(effective_direction, str)
            or effective_direction not in {"maximize", "minimize"}
        ):
            raise ValueError("selection metric/direction is not supported for this Lab task")
        nodes = [
            _node("profile"),
            _node("quality_gate", ("profile",)),
            _node("prepare", ("quality_gate",)),
        ]
        evaluations: list[str] = []
        for index, candidate_algorithm in enumerate(candidate_algorithms, start=1):
            train_id = f"train_{index}"
            evaluate_id = f"evaluate_{index}"
            nodes.append(
                PipelineNode(train_id, "train", ("prepare",), {"algorithm": candidate_algorithm})
            )
            nodes.append(PipelineNode(evaluate_id, "evaluate", (train_id,)))
            evaluations.append(evaluate_id)
        nodes.append(
            PipelineNode(
                "select",
                "select",
                tuple(evaluations),
                {"metric": metric, "direction": effective_direction},
            )
        )
        if register_model is not None:
            nodes.append(_registration_node(register_model))
        return PipelineIR(
            tuple(nodes), parameters=tuple(sorted(parameters.items())), schema=PIPELINE_SCHEMA_V2
        )

    if register_model is not None:
        if lab.task == "clustering":
            nodes = [
                _node("profile"),
                _node("quality_gate", ("profile",)),
                _node("prepare", ("quality_gate",)),
                PipelineNode("train", "train", ("prepare",), {"clusters": 2}),
                _node("evaluate", ("train",)),
                PipelineNode(
                    "select",
                    "select",
                    ("evaluate",),
                    {"metric": "calinski_harabasz", "direction": "maximize"},
                ),
                _registration_node(register_model),
            ]
        else:
            train_config = {"algorithm": algorithm} if algorithm is not None else {}
            nodes = [
                _node("profile"),
                _node("quality_gate", ("profile",)),
                _node("prepare", ("quality_gate",)),
                PipelineNode("train", "train", ("prepare",), train_config),
                _node("evaluate", ("train",)),
                PipelineNode(
                    "select",
                    "select",
                    ("evaluate",),
                    {
                        "metric": "accuracy" if lab.task == "classification" else "r2",
                        "direction": "maximize",
                    },
                ),
                _registration_node(register_model),
            ]
        return PipelineIR(
            tuple(nodes), parameters=tuple(sorted(parameters.items())), schema=PIPELINE_SCHEMA_V2
        )

    return PipelineIR(
        nodes=(
            _node("profile"),
            _node("quality_gate", ("profile",)),
            _node("prepare", ("quality_gate",)),
            _node("train", ("prepare",)),
            _node("evaluate", ("train",)),
            _node("select", ("evaluate",)),
        ),
        parameters=tuple(sorted(parameters.items())),
    )


@dataclass
class InMemoryMLLabStore(MLLabStore, FeatureDefinitionStore):
    _labs: dict[tuple[str, str], Lab] = field(default_factory=dict)
    _pipelines: dict[tuple[str, str], PipelineIR] = field(default_factory=dict)
    _feature_definitions: dict[tuple[str, str, int], FeatureDefinition] = field(default_factory=dict)
    _quality_suites: dict[tuple[str, str, str, int], QualitySuite] = field(default_factory=dict)
    _drift_policies: dict[tuple[str, str, str, int], DriftPolicy] = field(default_factory=dict)
    _lock: Any = field(default_factory=RLock, init=False, repr=False, compare=False)

    def put_lab(self, workspace_id: WorkspaceId, lab: Lab) -> Lab:
        with self._lock:
            key = (str(workspace_id), lab.id)
            current = self._labs.get(key)
            if current is not None and current != lab:
                raise MLLabConflict(f"lab id already exists: {lab.id}")
            self._labs[key] = lab
            return lab

    def get_lab(self, workspace_id: WorkspaceId, lab_id: str) -> Lab | None:
        with self._lock:
            return self._labs.get((str(workspace_id), lab_id))

    def list_labs(self, workspace_id: WorkspaceId) -> tuple[Lab, ...]:
        with self._lock:
            prefix = str(workspace_id)
            return tuple(
                sorted(
                    (lab for (workspace, _), lab in self._labs.items() if workspace == prefix),
                    key=lambda item: item.id,
                )
            )

    def put_pipeline(
        self, workspace_id: WorkspaceId, lab_id: str, pipeline: PipelineIR
    ) -> PipelineIR:
        with self._lock:
            self._pipelines[(str(workspace_id), lab_id)] = pipeline
            return pipeline

    def get_pipeline(self, workspace_id: WorkspaceId, lab_id: str) -> PipelineIR | None:
        with self._lock:
            return self._pipelines.get((str(workspace_id), lab_id))

    def put_feature_definition(
        self, workspace_id: WorkspaceId, definition: FeatureDefinition
    ) -> FeatureDefinition:
        with self._lock:
            workspace = str(workspace_id)
            key = (workspace, definition.id, definition.version)
            current = self._feature_definitions.get(key)
            if current is not None:
                if current != definition:
                    raise FeatureDefinitionConflict(
                        f"feature definition version already exists: {definition.id}/{definition.version}"
                    )
                return current
            latest = self.get_feature_definition(workspace_id, definition.id)
            if latest is not None and definition.version <= latest.version:
                raise FeatureDefinitionConflict(
                    f"feature definition version must advance: {definition.id}/{latest.version}"
                )
            self._feature_definitions[key] = definition
            return definition

    def get_feature_definition(
        self, workspace_id: WorkspaceId, feature_id: str, version: int | None = None
    ) -> FeatureDefinition | None:
        with self._lock:
            matches = [
                definition
                for (workspace, current_id, current_version), definition
                in self._feature_definitions.items()
                if workspace == str(workspace_id)
                and current_id == feature_id
                and (version is None or current_version == version)
            ]
            return max(matches, key=lambda item: item.version) if matches else None

    def list_feature_definitions(
        self, workspace_id: WorkspaceId, feature_id: str | None = None
    ) -> tuple[FeatureDefinition, ...]:
        with self._lock:
            return tuple(
                sorted(
                    (
                        definition
                        for (workspace, current_id, _), definition
                        in self._feature_definitions.items()
                        if workspace == str(workspace_id)
                        and (feature_id is None or current_id == feature_id)
                    ),
                    key=lambda item: (item.id, item.version),
                )
            )

    def put_quality_suite(
        self, workspace_id: WorkspaceId, lab_id: str, suite: QualitySuite
    ) -> QualitySuite:
        with self._lock:
            workspace = str(workspace_id)
            if self.get_lab(workspace_id, lab_id) is None:
                raise KeyError(lab_id)
            key = (workspace, lab_id, suite.id, suite.version)
            current = self._quality_suites.get(key)
            if current is not None:
                if current != suite:
                    raise QualitySuiteConflict(f"quality suite version already exists: {suite.id}@{suite.version}")
                return current
            latest = self.get_quality_suite(workspace_id, lab_id, suite.id)
            if latest is not None and suite.version <= latest.version:
                raise QualitySuiteConflict("quality suite versions must increase monotonically")
            self._quality_suites[key] = suite
            return suite

    def get_quality_suite(
        self, workspace_id: WorkspaceId, lab_id: str, suite_id: str, version: int | None = None
    ) -> QualitySuite | None:
        with self._lock:
            matches = [
                suite
                for (workspace, current_lab, current_id, current_version), suite
                in self._quality_suites.items()
                if workspace == str(workspace_id)
                and current_lab == lab_id
                and current_id == suite_id
                and (version is None or current_version == version)
            ]
            return max(matches, key=lambda suite: suite.version) if matches else None

    def list_quality_suites(
        self, workspace_id: WorkspaceId, lab_id: str
    ) -> tuple[QualitySuite, ...]:
        with self._lock:
            return tuple(
                sorted(
                    (
                        suite
                        for (workspace, current_lab, _, _), suite in self._quality_suites.items()
                        if workspace == str(workspace_id) and current_lab == lab_id
                    ),
                    key=lambda suite: (suite.id, suite.version),
                )
            )

    def put_drift_policy(
        self, workspace_id: WorkspaceId, lab_id: str, policy: DriftPolicy
    ) -> DriftPolicy:
        with self._lock:
            workspace = str(workspace_id)
            if self.get_lab(workspace_id, lab_id) is None:
                raise KeyError(lab_id)
            key = (workspace, lab_id, policy.id, policy.version)
            current = self._drift_policies.get(key)
            if current is not None:
                if current != policy:
                    raise DriftPolicyConflict(
                        f"drift policy version already exists: {policy.id}@{policy.version}"
                    )
                return current
            latest = self.get_drift_policy(workspace_id, lab_id, policy.id)
            if latest is not None and policy.version <= latest.version:
                raise DriftPolicyConflict("drift policy versions must increase monotonically")
            self._drift_policies[key] = policy
            return policy

    def get_drift_policy(
        self, workspace_id: WorkspaceId, lab_id: str, policy_id: str, version: int | None = None
    ) -> DriftPolicy | None:
        with self._lock:
            matches = [
                policy
                for (workspace, current_lab, current_id, current_version), policy
                in self._drift_policies.items()
                if workspace == str(workspace_id)
                and current_lab == lab_id
                and current_id == policy_id
                and (version is None or current_version == version)
            ]
            return max(matches, key=lambda policy: policy.version) if matches else None

    def list_drift_policies(
        self, workspace_id: WorkspaceId, lab_id: str
    ) -> tuple[DriftPolicy, ...]:
        with self._lock:
            return tuple(
                sorted(
                    (
                        policy
                        for (workspace, current_lab, _, _), policy in self._drift_policies.items()
                        if workspace == str(workspace_id) and current_lab == lab_id
                    ),
                    key=lambda policy: (policy.id, policy.version),
                )
            )


@dataclass(frozen=True, slots=True)
class LabService:
    store: MLLabStore

    def create(self, workspace_id: WorkspaceId, lab: Lab) -> Lab:
        if self.store.get_lab(workspace_id, lab.id) is not None:
            raise MLLabConflict(f"lab id already exists: {lab.id}")
        return self.store.put_lab(workspace_id, lab)

    def get(self, workspace_id: WorkspaceId, lab_id: str) -> Lab:
        lab = self.store.get_lab(workspace_id, lab_id)
        if lab is None:
            raise KeyError(lab_id)
        return lab

    def list(self, workspace_id: WorkspaceId) -> tuple[Lab, ...]:
        return self.store.list_labs(workspace_id)

    def put_pipeline(
        self, workspace_id: WorkspaceId, lab_id: str, pipeline: PipelineIR
    ) -> PipelineIR:
        lab = self.get(workspace_id, lab_id)
        if dict(pipeline.parameters).get("lab_digest") != lab.digest:
            raise ValueError("pipeline is not bound to the current Lab version")
        return self.store.put_pipeline(workspace_id, lab_id, pipeline)

    def compile(
        self,
        workspace_id: WorkspaceId,
        lab_id: str,
        *,
        algorithm: str | None = None,
        preprocessor: str = "identity",
        candidate_algorithms: tuple[str, ...] | None = None,
        candidate_cluster_counts: tuple[int, ...] | None = None,
        candidate_preprocessors: tuple[str, ...] | None = None,
        selection_metric: str | None = None,
        selection_direction: str | None = None,
        register_model: tuple[str, str] | None = None,
    ) -> PipelineIR:
        lab = self.get(workspace_id, lab_id)
        pipeline = compile_lab_pipeline(
            lab,
            algorithm=algorithm,
            preprocessor=preprocessor,
            candidate_algorithms=candidate_algorithms,
            candidate_cluster_counts=candidate_cluster_counts,
            candidate_preprocessors=candidate_preprocessors,
            selection_metric=selection_metric,
            selection_direction=selection_direction,
            register_model=register_model,
        )
        return self.store.put_pipeline(workspace_id, lab.id, pipeline)

    def put_quality_suite(
        self, workspace_id: WorkspaceId, lab_id: str, suite: QualitySuite
    ) -> QualitySuite:
        lab = self.get(workspace_id, lab_id)
        validate_quality_suite(lab, suite)
        return self.store.put_quality_suite(workspace_id, lab_id, suite)

    def get_quality_suite(
        self, workspace_id: WorkspaceId, lab_id: str, suite_id: str, version: int | None = None
    ) -> QualitySuite:
        self.get(workspace_id, lab_id)
        suite = self.store.get_quality_suite(workspace_id, lab_id, suite_id, version)
        if suite is None:
            raise KeyError(f"{suite_id}@{version}" if version is not None else suite_id)
        return suite

    def list_quality_suites(
        self, workspace_id: WorkspaceId, lab_id: str
    ) -> tuple[QualitySuite, ...]:
        self.get(workspace_id, lab_id)
        return self.store.list_quality_suites(workspace_id, lab_id)

    def put_drift_policy(
        self, workspace_id: WorkspaceId, lab_id: str, policy: DriftPolicy
    ) -> DriftPolicy:
        lab = self.get(workspace_id, lab_id)
        numeric_features = {feature.column for feature in lab.features if feature.role == "numeric"}
        if {item.feature for item in policy.thresholds} != numeric_features:
            raise ValueError("drift policy thresholds must define every numeric Lab feature exactly once")
        return self.store.put_drift_policy(workspace_id, lab_id, policy)

    def get_drift_policy(
        self, workspace_id: WorkspaceId, lab_id: str, policy_id: str, version: int | None = None
    ) -> DriftPolicy:
        self.get(workspace_id, lab_id)
        policy = self.store.get_drift_policy(workspace_id, lab_id, policy_id, version)
        if policy is None:
            raise KeyError(f"{policy_id}@{version}" if version is not None else policy_id)
        return policy

    def list_drift_policies(
        self, workspace_id: WorkspaceId, lab_id: str
    ) -> tuple[DriftPolicy, ...]:
        self.get(workspace_id, lab_id)
        return self.store.list_drift_policies(workspace_id, lab_id)


@dataclass(frozen=True, slots=True)
class FeatureDefinitionService:
    store: FeatureDefinitionStore

    def publish(
        self, workspace_id: WorkspaceId, definition: FeatureDefinition
    ) -> FeatureDefinition:
        current = self.store.get_feature_definition(workspace_id, definition.id, definition.version)
        if current is not None:
            if current != definition:
                raise FeatureDefinitionConflict(
                    f"feature definition version already exists: {definition.id}/{definition.version}"
                )
            return current
        latest = self.store.get_feature_definition(workspace_id, definition.id)
        if latest is not None and definition.version <= latest.version:
            raise FeatureDefinitionConflict(
                f"feature definition version must advance: {definition.id}/{latest.version}"
            )
        return self.store.put_feature_definition(workspace_id, definition)

    def publish_payload(self, workspace_id: WorkspaceId, payload: object) -> FeatureDefinition:
        return self.publish(workspace_id, FeatureDefinition.from_payload(payload))

    def get(
        self, workspace_id: WorkspaceId, feature_id: str, version: int | None = None
    ) -> FeatureDefinition:
        result = self.store.get_feature_definition(workspace_id, feature_id, version)
        if result is None:
            raise KeyError(feature_id)
        return result

    def list(
        self, workspace_id: WorkspaceId, feature_id: str | None = None
    ) -> tuple[FeatureDefinition, ...]:
        return self.store.list_feature_definitions(workspace_id, feature_id)


def _node(kind: str, depends_on: tuple[str, ...] = ()) -> PipelineNode:
    from typing import cast

    return PipelineNode(kind, cast(NodeKind, kind), depends_on)


def _registration_node(register_model: tuple[str, str]) -> PipelineNode:
    model_id, version = register_model
    return PipelineNode(
        "register", "register", ("select",), {"model_id": model_id, "version": version}
    )


__all__ = [
    "FeatureDefinitionConflict",
    "DriftPolicyConflict",
    "FeatureDefinitionService",
    "InMemoryMLLabStore",
    "LabService",
    "MLLabConflict",
    "QualitySuiteConflict",
]
