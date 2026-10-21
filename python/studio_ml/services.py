"""Application services and reference in-memory adapter for ML Studio."""
# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass, field

from studio_core import WorkspaceId

from .domain import (
    PIPELINE_SCHEMA_V2,
    FeatureDefinition,
    Lab,
    NodeKind,
    PipelineIR,
    PipelineNode,
)
from .ports import FeatureDefinitionStore, MLLabStore


class MLLabConflict(RuntimeError):
    """Raised when an immutable lab identity is reused with different content."""


class FeatureDefinitionConflict(RuntimeError):
    """Raised when a feature identity/version is reused with different content."""


def compile_lab_pipeline(
    lab: Lab,
    *,
    algorithm: str | None = None,
    preprocessor: str = "identity",
    candidate_algorithms: tuple[str, ...] | None = None,
    candidate_cluster_counts: tuple[int, ...] | None = None,
    selection_metric: str | None = None,
    selection_direction: str | None = None,
) -> PipelineIR:
    """Build the deterministic pipeline definition bound to an immutable Lab."""

    parameters = {
        "backend_id": lab.backend_id,
        "lab_digest": lab.digest,
        "seed": str(lab.seed),
        "task": lab.task,
    }
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

    if candidate_algorithms is not None and candidate_cluster_counts is not None:
        raise ValueError("candidate_algorithms cannot be combined with candidate_cluster_counts")
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
class InMemoryMLLabStore:
    _labs: dict[tuple[str, str], Lab] = field(default_factory=dict)
    _pipelines: dict[tuple[str, str], PipelineIR] = field(default_factory=dict)

    def put_lab(self, workspace_id: WorkspaceId, lab: Lab) -> Lab:
        key = (str(workspace_id), lab.id)
        current = self._labs.get(key)
        if current is not None and current != lab:
            raise MLLabConflict(f"lab id already exists: {lab.id}")
        self._labs[key] = lab
        return lab

    def get_lab(self, workspace_id: WorkspaceId, lab_id: str) -> Lab | None:
        return self._labs.get((str(workspace_id), lab_id))

    def list_labs(self, workspace_id: WorkspaceId) -> tuple[Lab, ...]:
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
        self._pipelines[(str(workspace_id), lab_id)] = pipeline
        return pipeline

    def get_pipeline(self, workspace_id: WorkspaceId, lab_id: str) -> PipelineIR | None:
        return self._pipelines.get((str(workspace_id), lab_id))


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

    def compile(
        self,
        workspace_id: WorkspaceId,
        lab_id: str,
        *,
        algorithm: str | None = None,
        preprocessor: str = "identity",
        candidate_algorithms: tuple[str, ...] | None = None,
        candidate_cluster_counts: tuple[int, ...] | None = None,
        selection_metric: str | None = None,
        selection_direction: str | None = None,
    ) -> PipelineIR:
        lab = self.get(workspace_id, lab_id)
        pipeline = compile_lab_pipeline(
            lab,
            algorithm=algorithm,
            preprocessor=preprocessor,
            candidate_algorithms=candidate_algorithms,
            candidate_cluster_counts=candidate_cluster_counts,
            selection_metric=selection_metric,
            selection_direction=selection_direction,
        )
        return self.store.put_pipeline(workspace_id, lab.id, pipeline)


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


__all__ = [
    "FeatureDefinitionConflict",
    "FeatureDefinitionService",
    "InMemoryMLLabStore",
    "LabService",
    "MLLabConflict",
]
