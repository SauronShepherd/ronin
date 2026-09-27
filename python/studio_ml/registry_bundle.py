"""Portable Bundle export/import for ML experiment and model-registry metadata."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from studio_core import WorkspaceId
from studio_core.bundle_inventory import (
    BUNDLE_INVENTORY_PATH,
    BundleInventory,
    BundleInventoryObject,
)
from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.ml import Experiment, MLRunRecord, RegisteredModelVersion
from studio_core.portability import RoninBundleManifest
from studio_orchestrator import Instant
from studio_storage.bundle import BundleFile, write_bundle
from studio_storage.bundle_payload import read_bundle_payload

INVENTORY_MEDIA_TYPE = "application/vnd.ronin.bundle-inventory+json"
MEDIA = {
    "experiment": "application/vnd.ronin.ml-experiment+json",
    "run": "application/vnd.ronin.ml-run+json",
    "model": "application/vnd.ronin.ml-model-version+json",
}


class MLRegistryBundleStore(Protocol):
    def list_experiments(self, workspace_id: WorkspaceId) -> tuple[Experiment, ...]: ...
    def list_runs(self, workspace_id: WorkspaceId) -> tuple[MLRunRecord, ...]: ...
    def list_models(self, workspace_id: WorkspaceId) -> tuple[RegisteredModelVersion, ...]: ...
    def put_experiment(
        self, workspace_id: WorkspaceId, experiment: Experiment, *, now: Instant | str
    ) -> Experiment: ...
    def record_run(
        self, workspace_id: WorkspaceId, run: MLRunRecord, *, now: Instant | str
    ) -> MLRunRecord: ...
    def register_model(
        self, workspace_id: WorkspaceId, model: RegisteredModelVersion, *, now: Instant | str
    ) -> RegisteredModelVersion: ...


@dataclass(frozen=True, slots=True)
class MLRegistryBundleImportPlan:
    inventory: BundleInventory
    experiments: tuple[Experiment, ...]
    runs: tuple[MLRunRecord, ...]
    models: tuple[RegisteredModelVersion, ...]


def _path(kind: str, identity: str) -> str:
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"objects/ml-registry/{kind}/{digest}.json"


def export_ml_registry_bundle(
    workspace_id: WorkspaceId, store: MLRegistryBundleStore, path: Path
) -> RoninBundleManifest:
    objects: list[BundleInventoryObject] = []
    files: list[BundleFile] = []
    for kind, values in (
        ("experiment", store.list_experiments(workspace_id)),
        ("run", store.list_runs(workspace_id)),
        ("model", store.list_models(workspace_id)),
    ):
        for value in values:
            identity = f"ml-{kind}:{workspace_id}/{_identity(kind, value)}"
            payload = value.to_json().encode("utf-8")
            object_path = _path(kind, identity)
            objects.append(BundleInventoryObject(f"ml_{kind}", identity, object_path))
            files.append(BundleFile(object_path, MEDIA[kind], payload))
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
    model = cast(RegisteredModelVersion, value)
    return f"{model.model_id}@{model.version}"


def plan_ml_registry_bundle_import(path: Path) -> MLRegistryBundleImportPlan:
    inventory_payload = read_bundle_payload(path, BUNDLE_INVENTORY_PATH)
    inventory = BundleInventory.from_payload(json.loads(inventory_payload.file.data))
    experiments: list[Experiment] = []
    runs: list[MLRunRecord] = []
    models: list[RegisteredModelVersion] = []
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
        else:
            models.append(RegisteredModelVersion.from_json(document))
    return MLRegistryBundleImportPlan(
        inventory,
        tuple(experiments),
        tuple(runs),
        tuple(models),
    )


def commit_ml_registry_bundle_import(
    path: Path, workspace_id: WorkspaceId, store: MLRegistryBundleStore, *, now: Instant | str
) -> MLRegistryBundleImportPlan:
    plan = plan_ml_registry_bundle_import(path)
    for experiment in plan.experiments:
        store.put_experiment(workspace_id, experiment, now=now)
    for run in plan.runs:
        store.record_run(workspace_id, run, now=now)
    for model in plan.models:
        store.register_model(workspace_id, model, now=now)
    return plan


__all__ = (
    "MLRegistryBundleImportPlan",
    "MLRegistryBundleStore",
    "commit_ml_registry_bundle_import",
    "export_ml_registry_bundle",
    "plan_ml_registry_bundle_import",
)
