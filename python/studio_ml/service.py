"""Application services connecting executable ML to Ronin experiment/registry metadata."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol, runtime_checkable

from studio_core import AssetRef, WorkspaceId
from studio_core.ml import (
    ExperimentId,
    MetricValue,
    MLRunId,
    MLRunRecord,
    ModelEvaluation,
    ModelId,
    ModelSignature,
    ModelVersion,
    RegisteredModelVersion,
)
from studio_orchestrator import Instant
from studio_storage.ports import ArtifactStore

from .runtime import TrainingSpec, predict_tabular, train_tabular


@runtime_checkable
class MLRegistryStore(Protocol):
    def record_evaluation(
        self, workspace_id: WorkspaceId, evaluation: ModelEvaluation, *, now: Instant | str
    ) -> ModelEvaluation: ...

    def list_evaluations(
        self, workspace_id: WorkspaceId, model_id: ModelId, version: ModelVersion
    ) -> tuple[ModelEvaluation, ...]: ...

    def record_run(
        self,
        workspace_id: WorkspaceId,
        run: MLRunRecord,
        *,
        now: Instant | str,
    ) -> MLRunRecord: ...

    def register_model(
        self,
        workspace_id: WorkspaceId,
        model: RegisteredModelVersion,
        *,
        now: Instant | str,
    ) -> RegisteredModelVersion: ...

    def get_model(
        self,
        workspace_id: WorkspaceId,
        model_id: ModelId,
        version: ModelVersion,
    ) -> RegisteredModelVersion | None: ...

    def get_champion_model(
        self, workspace_id: WorkspaceId, model_id: ModelId
    ) -> RegisteredModelVersion | None: ...

    def list_models(
        self, workspace_id: WorkspaceId, model_id: ModelId | None = None
    ) -> tuple[RegisteredModelVersion, ...]: ...

    def promote_model(
        self,
        workspace_id: WorkspaceId,
        model_id: ModelId,
        version: ModelVersion,
        *,
        now: Instant | str,
    ) -> RegisteredModelVersion: ...


class MLModelNotFound(KeyError):
    """Raised when inference references a model version absent from registry."""


def promote_registered_model(
    registry: MLRegistryStore,
    workspace_id: WorkspaceId,
    model_id: ModelId,
    model_version: ModelVersion,
    *,
    now: Instant | str,
) -> RegisteredModelVersion:
    """Promote a registered version using the registry's atomic stage transition."""

    return registry.promote_model(workspace_id, model_id, model_version, now=now)


def resolve_champion_model(
    registry: MLRegistryStore, workspace_id: WorkspaceId, model_id: ModelId
) -> RegisteredModelVersion:
    """Resolve the promoted model or fail explicitly when none exists."""

    model = registry.get_champion_model(workspace_id, model_id)
    if model is None:
        raise MLModelNotFound(f"{model_id}@champion")
    return model


def record_model_evaluation(
    registry: MLRegistryStore,
    workspace_id: WorkspaceId,
    evaluation: ModelEvaluation,
    *,
    now: Instant | str,
) -> ModelEvaluation:
    """Persist immutable evaluation evidence for a registered model version."""

    return registry.record_evaluation(workspace_id, evaluation, now=now)


def list_model_evaluations(
    registry: MLRegistryStore,
    workspace_id: WorkspaceId,
    model_id: ModelId,
    model_version: ModelVersion,
) -> tuple[ModelEvaluation, ...]:
    """List evaluation evidence for one registered model version."""

    return registry.list_evaluations(workspace_id, model_id, model_version)


def list_registered_models(
    registry: MLRegistryStore,
    workspace_id: WorkspaceId,
    model_id: ModelId | None = None,
) -> tuple[RegisteredModelVersion, ...]:
    """Return deterministic model-version metadata for catalog/deployment consumers."""

    return registry.list_models(workspace_id, model_id)


def _input_signature(
    rows: Sequence[Mapping[str, object]],
    features: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    if not rows:
        raise ValueError("ML signature inference requires at least one row")
    first = rows[0]
    result: list[tuple[str, str]] = []
    for feature in features:
        value = first[feature]
        if isinstance(value, bool):
            type_name = "bool"
        elif isinstance(value, int):
            type_name = "int64"
        elif isinstance(value, float):
            type_name = "float64"
        else:
            type_name = type(value).__name__
        result.append((feature, type_name))
    return tuple(result)


def _output_signature(task: str, target: str) -> tuple[tuple[str, str], ...]:
    return ((target, "label" if task == "classification" else "float64"),)


def train_register_tabular(
    registry: MLRegistryStore,
    artifacts: ArtifactStore,
    workspace_id: WorkspaceId,
    rows: Sequence[Mapping[str, object]],
    *,
    dataset: AssetRef,
    experiment_id: ExperimentId,
    run_id: MLRunId,
    model_id: ModelId,
    model_version: ModelVersion,
    source_revision: str,
    execution_ref: str,
    spec: TrainingSpec,
    now: Instant | str,
) -> RegisteredModelVersion:
    """Train, persist content-addressed artifact, record ML run, and register candidate model."""

    trained = train_tabular(rows, spec)
    artifact = artifacts.put_bytes(
        role="model",
        data=trained.artifact_bytes,
        media_type="application/vnd.ronin.sklearn-tabular+pickle",
    )
    run = MLRunRecord(
        run_id,
        experiment_id,
        execution_ref,
        source_revision,
        (dataset,),
        parameters=(
            ("algorithm", spec.algorithm),
            ("task", spec.task),
            ("target", spec.target),
            ("features", ",".join(spec.features)),
            ("random_seed", str(spec.random_seed)),
            ("test_fraction", str(spec.test_fraction)),
        ),
        metrics=tuple(MetricValue(name, value) for name, value in trained.metrics),
        artifact_refs=(artifact.storage_ref,),
    )
    registry.record_run(workspace_id, run, now=now)
    model = RegisteredModelVersion(
        model_id,
        model_version,
        run_id,
        artifact.storage_ref,
        artifact.digest,
        "sklearn",
        ModelSignature(
            _input_signature(rows, spec.features),
            _output_signature(spec.task, spec.target),
        ),
        "candidate",
    )
    return registry.register_model(workspace_id, model, now=now)


def predict_registered_tabular(
    registry: MLRegistryStore,
    workspace_id: WorkspaceId,
    model_id: ModelId,
    model_version: ModelVersion,
    artifact_bytes: bytes,
    rows: Sequence[Mapping[str, object]],
) -> tuple[object, ...]:
    """Verify bytes against registry metadata, then run trusted local inference.

    Artifact retrieval is deliberately kept outside this function because the current
    registered-model contract stores a content digest/ref but not the full ArtifactRef
    metadata required by every ArtifactStore implementation.
    """

    model = registry.get_model(workspace_id, model_id, model_version)
    if model is None:
        raise MLModelNotFound(f"{model_id}@{model_version}")
    if model.framework != "sklearn":
        raise ValueError(f"unsupported local inference framework: {model.framework}")
    digest = hashlib.sha256(artifact_bytes).hexdigest()
    if digest != model.artifact_digest:
        raise ValueError("model artifact digest does not match registered model")
    expected_features = tuple(name for name, _ in model.signature.inputs)
    return predict_tabular(
        artifact_bytes,
        rows,
        expected_features=expected_features,
    )


def predict_champion_tabular(
    registry: MLRegistryStore,
    workspace_id: WorkspaceId,
    model_id: ModelId,
    rows: Sequence[Mapping[str, object]],
    *,
    load_artifact: Callable[[str], bytes],
) -> tuple[object, ...]:
    """Resolve the champion, load its referenced artifact, and verify it before inference."""

    model = resolve_champion_model(registry, workspace_id, model_id)
    artifact_bytes = load_artifact(model.artifact_ref)
    return predict_registered_tabular(
        registry,
        workspace_id,
        model.model_id,
        model.version,
        artifact_bytes,
        rows,
    )


__all__ = (
    "MLModelNotFound",
    "MLRegistryStore",
    "promote_registered_model",
    "resolve_champion_model",
    "list_registered_models",
    "record_model_evaluation",
    "list_model_evaluations",
    "predict_registered_tabular",
    "predict_champion_tabular",
    "train_register_tabular",
)
