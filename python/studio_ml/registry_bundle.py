"""Portable Bundle export/import for ML experiment and model-registry metadata."""

from __future__ import annotations

import base64
import hashlib
from contextlib import nullcontext
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol, cast

from studio_core import WorkspaceId
from studio_core.bundle_inventory import (
    BUNDLE_INVENTORY_PATH,
    BundleInventory,
    BundleInventoryObject,
)
from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.ml import (
    Experiment,
    MLRunRecord,
    ModelEvaluation,
    ModelId,
    ModelVersion,
    RegisteredModelVersion,
)
from studio_core.portability import RoninBundleManifest
from studio_orchestrator import Instant
from studio_storage.bundle import BundleFile, write_bundle
from studio_storage.bundle_payload import read_bundle_payload
from studio_storage.ports import ArtifactReferenceBarrier

from .domain import FeatureDefinition
from .ports import FeatureDefinitionStore

INVENTORY_MEDIA_TYPE = "application/vnd.ronin.bundle-inventory+json"
MEDIA = {
    "experiment": "application/vnd.ronin.ml-experiment+json",
    "run": "application/vnd.ronin.ml-run+json",
    "model": "application/vnd.ronin.ml-model-version+json",
    "feature": "application/vnd.ronin.ml-feature+json",
    "evaluation": "application/vnd.ronin.ml-evaluation+json",
    "artifact": "application/vnd.ronin.ml-artifact+json",
}


class MLRegistryBundleStore(Protocol):
    def list_experiments(self, workspace_id: WorkspaceId) -> tuple[Experiment, ...]: ...
    def list_runs(self, workspace_id: WorkspaceId) -> tuple[MLRunRecord, ...]: ...
    def list_models(self, workspace_id: WorkspaceId) -> tuple[RegisteredModelVersion, ...]: ...
    def list_evaluations(
        self, workspace_id: WorkspaceId, model_id: ModelId, version: ModelVersion
    ) -> tuple[ModelEvaluation, ...]: ...
    def put_experiment(
        self, workspace_id: WorkspaceId, experiment: Experiment, *, now: Instant | str
    ) -> Experiment: ...
    def record_run(
        self, workspace_id: WorkspaceId, run: MLRunRecord, *, now: Instant | str
    ) -> MLRunRecord: ...
    def register_model(
        self, workspace_id: WorkspaceId, model: RegisteredModelVersion, *, now: Instant | str
    ) -> RegisteredModelVersion: ...


class MLRegistryBundleArtifactStore(Protocol):
    def get_bytes_by_storage_ref(self, storage_ref: str, *, digest: str) -> bytes: ...

    def put_bytes(self, *, role: str, data: bytes, media_type: str | None = None) -> object: ...


@dataclass(frozen=True, slots=True)
class MLRegistryBundleArtifact:
    source_ref: str
    digest: str
    role: str
    media_type: str | None
    data: bytes

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_ref, str)
            or not isinstance(self.role, str)
            or not self.source_ref.strip()
            or not self.role.strip()
            or not isinstance(self.data, bytes)
        ):
            raise ValueError("ML bundle artifact identity is invalid")
        if len(self.digest) != 64 or any(char not in "0123456789abcdef" for char in self.digest):
            raise ValueError("ML bundle artifact digest is invalid")
        if hashlib.sha256(self.data).hexdigest() != self.digest:
            raise ValueError("ML bundle artifact digest does not match its bytes")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "ronin.ml-artifact/v1",
            "source_ref": self.source_ref,
            "digest": self.digest,
            "role": self.role,
            "media_type": self.media_type,
            "data_base64": base64.b64encode(self.data).decode("ascii"),
        }

    @classmethod
    def from_payload(cls, payload: object) -> MLRegistryBundleArtifact:
        if not isinstance(payload, dict) or set(payload) != {
            "schema",
            "source_ref",
            "digest",
            "role",
            "media_type",
            "data_base64",
        }:
            raise ValueError("ML bundle artifact has invalid shape")
        encoded = payload["data_base64"]
        if (
            payload["schema"] != "ronin.ml-artifact/v1"
            or not all(isinstance(payload[key], str) for key in ("source_ref", "digest", "role"))
            or not isinstance(encoded, str)
            or not isinstance(payload["media_type"], (str, type(None)))
        ):
            raise ValueError("ML bundle artifact fields have invalid types")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("ML bundle artifact data is invalid base64") from exc
        return cls(
            cast(str, payload["source_ref"]),
            cast(str, payload["digest"]),
            cast(str, payload["role"]),
            cast(str | None, payload["media_type"]),
            data,
        )


@dataclass(frozen=True, slots=True)
class MLRegistryBundleImportPlan:
    inventory: BundleInventory
    experiments: tuple[Experiment, ...]
    runs: tuple[MLRunRecord, ...]
    models: tuple[RegisteredModelVersion, ...]
    artifacts: tuple[MLRegistryBundleArtifact, ...] = ()
    features: tuple[FeatureDefinition, ...] = ()
    evaluations: tuple[ModelEvaluation, ...] = ()


def _path(kind: str, identity: str) -> str:
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"objects/ml-registry/{kind}/{digest}.json"


def export_ml_registry_bundle(
    workspace_id: WorkspaceId,
    store: MLRegistryBundleStore,
    path: Path,
    *,
    artifact_store: MLRegistryBundleArtifactStore | None = None,
    feature_store: FeatureDefinitionStore | None = None,
) -> RoninBundleManifest:
    objects: list[BundleInventoryObject] = []
    files: list[BundleFile] = []
    experiments = store.list_experiments(workspace_id)
    runs = store.list_runs(workspace_id)
    models = store.list_models(workspace_id)
    features = (
        feature_store.list_feature_definitions(workspace_id) if feature_store is not None else ()
    )
    list_evaluations = getattr(store, "list_evaluations", None)
    evaluations: tuple[ModelEvaluation, ...] = ()
    if callable(list_evaluations):
        evaluations = tuple(
            evaluation
            for model in models
            for evaluation in list_evaluations(workspace_id, model.model_id, model.version)
        )
    model_by_ref: dict[str, RegisteredModelVersion] = {}
    for model in models:
        existing = model_by_ref.get(model.artifact_ref)
        if existing is not None and existing.artifact_digest != model.artifact_digest:
            raise ValueError("ML bundle reuses an artifact reference with conflicting digests")
        model_by_ref[model.artifact_ref] = model
    artifacts: dict[str, MLRegistryBundleArtifact] = {}
    if artifact_store is not None:
        getter = getattr(artifact_store, "get_bytes_by_storage_ref", None)
        if not callable(getter):
            raise ValueError("artifact store cannot export ML bundle bytes")
        referenced_refs = {artifact_ref for run in runs for artifact_ref in run.artifact_refs} | {
            model.artifact_ref for model in models
        }
        for source_ref in sorted(referenced_refs):
            model_record = model_by_ref.get(source_ref)
            if model_record is None:
                raise ValueError(
                    "ML bundle cannot verify an artifact reference without model digest metadata"
                )
            data = getter(source_ref, digest=model_record.artifact_digest)
            if not isinstance(data, bytes):
                raise ValueError("ML bundle artifact store returned non-byte data")
            media_type = (
                "application/vnd.ronin.sklearn-tabular+json"
                if model.framework == "sklearn"
                else "application/vnd.ronin.ml-kmeans+json"
                if model.framework == "ronin-kmeans"
                else "application/octet-stream"
            )
            artifacts[source_ref] = MLRegistryBundleArtifact(
                source_ref,
                model_record.artifact_digest,
                "model",
                media_type,
                data,
            )
    values_by_kind: tuple[tuple[str, tuple[object, ...]], ...] = (
        ("experiment", tuple(experiments)),
        ("feature", tuple(features)),
        ("run", tuple(runs)),
        ("model", tuple(models)),
        ("evaluation", tuple(evaluations)),
    )
    artifact_refs = {
        ref: f"ml-artifact:{workspace_id}/{artifact.digest}/{hashlib.sha256(ref.encode('utf-8')).hexdigest()[:16]}"
        for ref, artifact in artifacts.items()
    }
    experiment_refs = {
        str(experiment.id): f"ml-experiment:{workspace_id}/{experiment.id}"
        for experiment in experiments
    }
    run_refs = {str(run.id): f"ml-run:{workspace_id}/{run.id}" for run in runs}
    for kind, values in values_by_kind:
        for value in values:
            identity = f"ml-{kind}:{workspace_id}/{_identity(kind, value)}"
            to_json = getattr(value, "to_json", None)
            if not callable(to_json):
                raise ValueError(f"ML bundle {kind} record cannot be serialized")
            payload = to_json().encode("utf-8")
            object_path = _path(kind, identity)
            dependencies: set[str] = set()
            if kind == "run":
                dependencies.add(experiment_refs[str(cast(MLRunRecord, value).experiment_id)])
                dependencies.update(
                    artifact_refs.get(ref, "") for ref in cast(MLRunRecord, value).artifact_refs
                )
            elif kind == "model":
                model = cast(RegisteredModelVersion, value)
                dependencies.add(run_refs[str(model.source_run_id)])
                if model.artifact_ref in artifact_refs:
                    dependencies.add(artifact_refs[model.artifact_ref])
            elif kind == "evaluation":
                evaluation = cast(ModelEvaluation, value)
                dependencies.add(
                    f"ml-model:{workspace_id}/{evaluation.model_id}@{evaluation.version}"
                )
            dependencies.discard("")
            objects.append(
                BundleInventoryObject(
                    f"ml_{kind}", identity, object_path, tuple(sorted(dependencies))
                )
            )
            files.append(BundleFile(object_path, MEDIA[kind], payload))
    for artifact in artifacts.values():
        identity = artifact_refs[artifact.source_ref]
        object_path = _path("artifact", identity)
        objects.append(BundleInventoryObject("ml_artifact", identity, object_path))
        files.append(
            BundleFile(
                object_path,
                MEDIA["artifact"],
                encode_canonical_json(artifact.to_payload()),
            )
        )
    inventory = BundleInventory(tuple(objects))
    files.append(
        BundleFile(
            BUNDLE_INVENTORY_PATH,
            INVENTORY_MEDIA_TYPE,
            encode_canonical_json(inventory.to_payload()),
        )
    )
    return write_bundle(path, tuple(sorted(files, key=lambda item: item.path)))


def _identity(kind: str, value: object) -> str:
    if kind == "experiment":
        return str(cast(Experiment, value).id)
    if kind == "run":
        return str(cast(MLRunRecord, value).id)
    if kind == "feature":
        definition = cast(FeatureDefinition, value)
        return f"{definition.id}@{definition.version}"
    if kind == "evaluation":
        evaluation = cast(ModelEvaluation, value)
        return f"{evaluation.model_id}@{evaluation.version}/{evaluation.execution_ref}"
    model = cast(RegisteredModelVersion, value)
    return f"{model.model_id}@{model.version}"


def plan_ml_registry_bundle_import(path: Path) -> MLRegistryBundleImportPlan:
    inventory_payload = read_bundle_payload(path, BUNDLE_INVENTORY_PATH)
    inventory = BundleInventory.from_payload(decode_canonical_json(inventory_payload.file.data))
    experiments: list[Experiment] = []
    runs: list[MLRunRecord] = []
    models: list[RegisteredModelVersion] = []
    artifacts: list[MLRegistryBundleArtifact] = []
    features: list[FeatureDefinition] = []
    evaluations: list[ModelEvaluation] = []
    for item in inventory.objects:
        payload = read_bundle_payload(path, item.path)
        if payload.manifest != inventory_payload.manifest:
            raise ValueError("ML registry Bundle changed while import plan was constructed")
        kind = item.kind.removeprefix("ml_")
        if kind not in MEDIA or payload.file.media_type != MEDIA[kind]:
            raise ValueError("unsupported ML registry Bundle object or media type")
        document = payload.file.data.decode("utf-8")
        if kind == "experiment":
            experiments.append(Experiment.from_json(document))
        elif kind == "run":
            runs.append(MLRunRecord.from_json(document))
        elif kind == "model":
            models.append(RegisteredModelVersion.from_json(document))
        elif kind == "feature":
            features.append(FeatureDefinition.from_json(document))
        elif kind == "evaluation":
            evaluations.append(ModelEvaluation.from_json(document))
        else:
            artifacts.append(MLRegistryBundleArtifact.from_payload(decode_canonical_json(document)))
    artifact_by_ref = {artifact.source_ref: artifact for artifact in artifacts}
    if len(artifact_by_ref) != len(artifacts):
        raise ValueError("ML registry Bundle contains duplicate artifact references")
    model_refs = {model.artifact_ref: model.artifact_digest for model in models}
    if artifacts and set(model_refs) != set(artifact_by_ref):
        raise ValueError("ML registry Bundle does not contain every referenced model artifact")
    if artifacts and any(
        reference not in artifact_by_ref for run in runs for reference in run.artifact_refs
    ):
        raise ValueError("ML registry Bundle run references an absent artifact")
    for artifact in artifacts:
        if model_refs.get(artifact.source_ref) != artifact.digest:
            raise ValueError("ML registry Bundle artifact is not bound to a model digest")
    experiment_ids = {str(experiment.id) for experiment in experiments}
    run_ids = {str(run.id) for run in runs}
    model_keys = {f"{model.model_id}@{model.version}" for model in models}
    if any(str(run.experiment_id) not in experiment_ids for run in runs):
        raise ValueError("ML registry Bundle run references an absent experiment")
    if any(str(model.source_run_id) not in run_ids for model in models):
        raise ValueError("ML registry Bundle model references an absent run")
    if any(
        str(evaluation.model_id) + "@" + str(evaluation.version) not in model_keys
        for evaluation in evaluations
    ):
        raise ValueError("ML registry Bundle evaluation references an absent model")
    return MLRegistryBundleImportPlan(
        inventory,
        tuple(experiments),
        tuple(runs),
        tuple(models),
        tuple(sorted(artifacts, key=lambda item: item.source_ref)),
        tuple(sorted(features, key=lambda item: (item.id, item.version))),
        tuple(
            sorted(
                evaluations,
                key=lambda item: (str(item.model_id), str(item.version), item.execution_ref),
            )
        ),
    )


def commit_ml_registry_bundle_import(
    path: Path,
    workspace_id: WorkspaceId,
    store: MLRegistryBundleStore,
    *,
    now: Instant | str,
    artifact_store: MLRegistryBundleArtifactStore | None = None,
    feature_store: FeatureDefinitionStore | None = None,
    artifact_reference_barrier: ArtifactReferenceBarrier | None = None,
) -> MLRegistryBundleImportPlan:
    """Commit a validated bundle while fencing artifact bytes and references.

    PostgreSQL compositions pass the same shared barrier used by every other
    artifact producer.  The lease spans artifact materialization and all
    durable registry/feature references, so a collector cannot observe the
    import half-published.  SQLite and metadata-only imports retain the
    existing behavior when no barrier is supplied.
    """

    lease = (
        artifact_reference_barrier.writer()
        if artifact_reference_barrier is not None
        else nullcontext()
    )
    with lease:
        return _commit_ml_registry_bundle_import(
            path,
            workspace_id,
            store,
            now=now,
            artifact_store=artifact_store,
            feature_store=feature_store,
        )


def _commit_ml_registry_bundle_import(
    path: Path,
    workspace_id: WorkspaceId,
    store: MLRegistryBundleStore,
    *,
    now: Instant | str,
    artifact_store: MLRegistryBundleArtifactStore | None = None,
    feature_store: FeatureDefinitionStore | None = None,
) -> MLRegistryBundleImportPlan:
    plan = plan_ml_registry_bundle_import(path)
    if plan.features and feature_store is None:
        raise ValueError(
            "ML registry Bundle contains feature definitions but no feature store was supplied"
        )
    record_evaluation = getattr(store, "record_evaluation", None)
    if plan.evaluations and not callable(record_evaluation):
        raise ValueError("ML registry Bundle contains evaluations but registry cannot store them")
    artifact_refs: dict[str, str] = {}
    if plan.artifacts:
        if artifact_store is None:
            raise ValueError(
                "ML registry Bundle contains artifacts but no artifact store was supplied"
            )
        for artifact in plan.artifacts:
            stored = artifact_store.put_bytes(
                role=artifact.role,
                data=artifact.data,
                media_type=artifact.media_type,
            )
            storage_ref = getattr(stored, "storage_ref", None)
            if not isinstance(storage_ref, str) or not storage_ref.strip():
                raise ValueError("artifact store returned an invalid storage reference")
            artifact_refs[artifact.source_ref] = storage_ref
    for experiment in plan.experiments:
        store.put_experiment(workspace_id, experiment, now=now)
    if plan.features:
        if feature_store is None:
            raise RuntimeError("feature store disappeared during bundle import")
        for definition in plan.features:
            feature_store.put_feature_definition(workspace_id, definition)
    for run in plan.runs:
        if artifact_refs:
            run = replace(
                run,
                artifact_refs=tuple(artifact_refs.get(ref, ref) for ref in run.artifact_refs),
            )
        store.record_run(workspace_id, run, now=now)
    for model in plan.models:
        if model.artifact_ref in artifact_refs:
            model = replace(model, artifact_ref=artifact_refs[model.artifact_ref])
        store.register_model(workspace_id, model, now=now)
    for evaluation in plan.evaluations:
        if not callable(record_evaluation):
            raise RuntimeError("evaluation recorder disappeared during bundle import")
        record_evaluation(workspace_id, evaluation, now=now)
    return plan


__all__ = (
    "MLRegistryBundleArtifact",
    "MLRegistryBundleArtifactStore",
    "MLRegistryBundleImportPlan",
    "MLRegistryBundleStore",
    "commit_ml_registry_bundle_import",
    "export_ml_registry_bundle",
    "plan_ml_registry_bundle_import",
)
