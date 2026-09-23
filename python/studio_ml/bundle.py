"""Deterministic Bundle portability for ML lab and pipeline intent."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from studio_core import WorkspaceId
from studio_core.bundle_inventory import (
    BUNDLE_INVENTORY_PATH,
    BundleInventory,
    BundleInventoryObject,
)
from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.portability import RoninBundleManifest
from studio_storage.bundle import BundleFile, write_bundle
from studio_storage.bundle_payload import read_bundle_payload

from .domain import Lab, PipelineIR

INVENTORY_MEDIA_TYPE = "application/vnd.ronin.bundle-inventory+json"
LAB_MEDIA_TYPE = "application/vnd.ronin.ml-lab+json"
PIPELINE_MEDIA_TYPE = "application/vnd.ronin.ml-pipeline+json"


class MLBundleStore(Protocol):
    def list_labs(self, workspace_id: WorkspaceId) -> tuple[Lab, ...]: ...
    def get_pipeline(self, workspace_id: WorkspaceId, lab_id: str) -> PipelineIR | None: ...
    def put_lab(self, workspace_id: WorkspaceId, lab: Lab) -> Lab: ...
    def put_pipeline(
        self, workspace_id: WorkspaceId, lab_id: str, pipeline: PipelineIR
    ) -> PipelineIR: ...


@dataclass(frozen=True, slots=True)
class MLBundleImportPlan:
    inventory: BundleInventory
    labs: tuple[Lab, ...]
    pipelines: tuple[tuple[str, PipelineIR], ...]


def _path(kind: str, ref: str) -> str:
    return f"objects/ml/{kind}/{hashlib.sha256(ref.encode('utf-8')).hexdigest()}.json"


def export_ml_bundle(
    workspace_id: WorkspaceId, store: MLBundleStore, path: Path
) -> RoninBundleManifest:
    objects: list[BundleInventoryObject] = []
    files: list[BundleFile] = []
    for lab in sorted(store.list_labs(workspace_id), key=lambda item: item.id):
        lab_ref = f"ml-lab:{workspace_id}/{lab.id}"
        lab_path = _path("lab", lab_ref)
        objects.append(BundleInventoryObject("ml_lab", lab_ref, lab_path))
        files.append(BundleFile(lab_path, LAB_MEDIA_TYPE, lab.to_json().encode("utf-8")))
        pipeline = store.get_pipeline(workspace_id, lab.id)
        if pipeline is not None:
            pipeline_ref = f"ml-pipeline:{workspace_id}/{lab.id}"
            pipeline_path = _path("pipeline", pipeline_ref)
            objects.append(
                BundleInventoryObject("ml_pipeline", pipeline_ref, pipeline_path, (lab_ref,))
            )
            files.append(
                BundleFile(pipeline_path, PIPELINE_MEDIA_TYPE, pipeline.to_json().encode("utf-8"))
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


def plan_ml_bundle_import(path: Path) -> MLBundleImportPlan:
    inventory_payload = read_bundle_payload(path, BUNDLE_INVENTORY_PATH)
    inventory = BundleInventory.from_payload(json.loads(inventory_payload.file.data))
    labs: list[Lab] = []
    pipelines: list[tuple[str, PipelineIR]] = []
    for item in inventory.objects:
        payload = read_bundle_payload(path, item.path)
        if payload.manifest != inventory_payload.manifest:
            raise ValueError("ML Bundle changed while import plan was constructed")
        if item.kind == "ml_lab" and payload.file.media_type == LAB_MEDIA_TYPE:
            labs.append(Lab.from_json(payload.file.data.decode("utf-8")))
        elif item.kind == "ml_pipeline" and payload.file.media_type == PIPELINE_MEDIA_TYPE:
            lab_id = item.logical_ref.rsplit("/", 1)[-1]
            pipelines.append((lab_id, PipelineIR.from_json(payload.file.data.decode("utf-8"))))
        else:
            raise ValueError("unsupported ML Bundle object or media type")
    return MLBundleImportPlan(inventory, tuple(labs), tuple(pipelines))


def commit_ml_bundle_import(
    path: Path, workspace_id: WorkspaceId, store: MLBundleStore
) -> MLBundleImportPlan:
    plan = plan_ml_bundle_import(path)
    existing = {lab.id: lab for lab in store.list_labs(workspace_id)}
    for lab in plan.labs:
        if lab.id in existing and existing[lab.id] != lab:
            raise ValueError(f"ML lab conflicts with existing definition: {lab.id}")
    for lab in plan.labs:
        store.put_lab(workspace_id, lab)
    for lab_id, pipeline in plan.pipelines:
        store.put_pipeline(workspace_id, lab_id, pipeline)
    return plan


__all__ = (
    "MLBundleImportPlan",
    "commit_ml_bundle_import",
    "export_ml_bundle",
    "plan_ml_bundle_import",
)
