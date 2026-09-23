"""Application services connecting executable ML to Ronin experiment/registry metadata."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol, runtime_checkable

from studio_core import AssetRef, WorkspaceId
from studio_core.ml import (
    Experiment,
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

from .domain import Lab
from .runner import ClusteringResult, ExperimentResult
from .runtime import TrainingSpec, predict_tabular, train_tabular


@runtime_checkable
class MLRegistryStore(Protocol):
    def get_run(self, workspace_id: WorkspaceId, run_id: MLRunId) -> MLRunRecord | None: ...

    def put_experiment(
        self, workspace_id: WorkspaceId, experiment: Experiment, *, now: Instant | str
    ) -> Experiment: ...
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


def persist_experiment_result(
    registry: MLRegistryStore,
    workspace_id: WorkspaceId,
    lab: Lab,
    result: ExperimentResult,
    *,
    run_id: MLRunId,
    execution_ref: str,
    source_revision: str,
    now: Instant | str,
) -> MLRunRecord:
    """Persist the experiment identity and its immutable run provenance."""
    from .provenance import run_record

    registry.put_experiment(
        workspace_id,
        Experiment(ExperimentId(lab.id), lab.name, lab.project_id),
        now=now,
    )
    record = run_record(
        lab,
        result,
        run_id=run_id.value,
        execution_ref=execution_ref,
        source_revision=source_revision,
    )
    return registry.record_run(workspace_id, record, now=now)


def persist_clustering_result(
    registry: MLRegistryStore,
    artifacts: ArtifactStore,
    workspace_id: WorkspaceId,
    lab: Lab,
    result: ClusteringResult,
    *,
    run_id: MLRunId,
    execution_ref: str,
    source_revision: str,
    now: Instant | str,
) -> MLRunRecord:
    """Persist a K-Means artifact and immutable clustering run provenance."""
    artifact_bytes = json.dumps(
        result.model.to_artifact(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    artifact = artifacts.put_bytes(
        role="model",
        data=artifact_bytes,
        media_type="application/vnd.ronin.ml-kmeans+json",
    )
    registry.put_experiment(
        workspace_id,
        Experiment(ExperimentId(lab.id), lab.name, lab.project_id),
        now=now,
    )
    record = MLRunRecord(
        id=run_id,
        experiment_id=ExperimentId(lab.id),
        execution_ref=execution_ref,
        source_revision=source_revision,
        datasets=(lab.dataset,),
        parameters=(
            ("algorithm", "kmeans"),
            ("backend_id", result.backend_id),
            ("task", "clustering"),
            ("features", ",".join(result.features)),
            ("iterations", str(result.model.iterations)),
        ),
        metrics=(MetricValue("inertia", result.inertia),),
        artifact_refs=(artifact.storage_ref,),
    )
    return registry.record_run(workspace_id, record, now=now)


def register_clustering_model(
    registry: MLRegistryStore,
    artifacts: ArtifactStore,
    workspace_id: WorkspaceId,
    lab: Lab,
    result: ClusteringResult,
    *,
    run_id: MLRunId,
    model_id: ModelId,
    model_version: ModelVersion,
    now: Instant | str,
) -> RegisteredModelVersion:
    """Register a persisted K-Means artifact as a candidate model version."""
    del lab
    artifact_bytes = json.dumps(
        result.model.to_artifact(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    artifact = artifacts.put_bytes(
        role="model", data=artifact_bytes, media_type="application/vnd.ronin.ml-kmeans+json"
    )
    signature = ModelSignature(
        _input_signature([dict.fromkeys(result.features, 0.0)], result.features),
        (("cluster", "int64"),),
    )
    return registry.register_model(
        workspace_id,
        RegisteredModelVersion(
            model_id,
            model_version,
            run_id,
            artifact.storage_ref,
            artifact.digest,
            "ronin-kmeans",
            signature,
            "candidate",
        ),
        now=now,
    )


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


def compare_model_evaluations(
    evaluations: Sequence[ModelEvaluation],
    *,
    metric: str,
    higher_is_better: bool = True,
) -> tuple[ModelEvaluation, ...]:
    """Return deterministic evaluation ranking without inventing missing metrics."""
    if not metric.strip():
        raise ValueError("metric must be non-empty")
    selected: list[tuple[ModelEvaluation, float]] = []
    for evaluation in evaluations:
        values = [item.value for item in evaluation.metrics if item.name == metric]
        if not values:
            continue
        selected.append((evaluation, values[-1]))
    selected.sort(
        key=lambda item: (
            -item[1] if higher_is_better else item[1],
            item[0].model_id.value,
            item[0].version.value,
            item[0].execution_ref,
        )
    )
    return tuple(item[0] for item in selected)


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
        media_type="application/vnd.ronin.sklearn-tabular+json",
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
    """Verify registered digest provenance before canonical local inference.

    Artifact retrieval is deliberately kept outside this function because the current
    registered-model contract stores a content digest/ref but not the full ArtifactRef
    metadata required by every ArtifactStore implementation.
    """

    model = registry.get_model(workspace_id, model_id, model_version)
    if model is None:
        raise MLModelNotFound(f"{model_id}@{model_version}")
    if model.framework not in {"sklearn", "ronin-kmeans"}:
        raise ValueError(f"unsupported local inference framework: {model.framework}")
    digest = hashlib.sha256(artifact_bytes).hexdigest()
    if digest != model.artifact_digest:
        raise ValueError("model artifact digest does not match registered model")
    expected_features = tuple(name for name, _ in model.signature.inputs)
    try:
        payload = json.loads(artifact_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None
    if isinstance(payload, dict) and payload.get("schema") == "ronin.ml-kmeans/v1":
        centroids = payload.get("centroids")
        if not isinstance(centroids, list) or not centroids:
            raise ValueError("K-Means artifact has invalid centroids")
        from .clustering import KMeansModel

        try:
            model_kmeans = KMeansModel(
                tuple(tuple(float(value) for value in centroid) for centroid in centroids),
                int(payload.get("iterations", 0)),
            )
        except (TypeError, ValueError):
            raise ValueError("K-Means artifact has invalid centroids") from None
        return tuple(model_kmeans.predict(rows, expected_features))
    return predict_tabular(artifact_bytes, rows, expected_features=expected_features)


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
    "compare_model_evaluations",
    "predict_registered_tabular",
    "predict_champion_tabular",
    "train_register_tabular",
)
