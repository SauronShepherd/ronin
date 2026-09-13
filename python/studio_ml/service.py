"""Application services connecting executable ML to Ronin experiment/registry metadata."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from studio_core import AssetRef, WorkspaceId
from studio_core.ml import (
    ExperimentId,
    MLRunId,
    MLRunRecord,
    MetricValue,
    ModelId,
    ModelSignature,
    ModelVersion,
    RegisteredModelVersion,
)
from studio_orchestrator import Instant
from studio_storage.artifacts import ArtifactRef
from studio_storage.ports import ArtifactStore

from .runtime import TrainingSpec, predict_tabular, train_tabular


@runtime_checkable
class MLRegistryStore(Protocol):
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


class MLModelNotFound(KeyError):
    """Raised when inference references a model version absent from registry."""


def _input_signature(rows: Sequence[Mapping[str, object]], features: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
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
    artifacts: ArtifactStore,
    workspace_id: WorkspaceId,
    model_id: ModelId,
    model_version: ModelVersion,
    rows: Sequence[Mapping[str, object]],
) -> tuple[object, ...]:
    """Load a registered content-addressed model artifact and run bounded local inference."""

    model = registry.get_model(workspace_id, model_id, model_version)
    if model is None:
        raise MLModelNotFound(f"{model_id}@{model_version}")
    if model.framework != "sklearn":
        raise ValueError(f"unsupported local inference framework: {model.framework}")
    artifact = ArtifactRef(
        role="model",
        digest_algorithm="sha256",
        digest=model.artifact_digest,
        media_type="application/vnd.ronin.sklearn-tabular+pickle",
        size_bytes=0,
        storage_ref=model.artifact_ref,
    )
    # ArtifactStore implementations validate integrity; size is not part of registry metadata yet.
    data = artifacts.get_bytes(artifact)
    expected_features = tuple(name for name, _ in model.signature.inputs)
    return predict_tabular(data, rows, expected_features=expected_features)


__all__ = (
    "MLModelNotFound",
    "MLRegistryStore",
    "predict_registered_tabular",
    "train_register_tabular",
)
