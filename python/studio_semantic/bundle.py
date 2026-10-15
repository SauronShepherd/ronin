"""Deterministic, definition-only Bundle portability for semantic assets."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from studio_core.bundle_inventory import (
    BUNDLE_INVENTORY_PATH,
    BundleInventory,
    BundleInventoryObject,
)
from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.portability import RoninBundleManifest
from studio_storage.bundle import BundleFile, write_bundle
from studio_storage.bundle_payload import read_bundle_payload

from .contracts import DashboardDefinition, SemanticModel

INVENTORY_MEDIA_TYPE = "application/vnd.ronin.bundle-inventory+json"
MODEL_MEDIA_TYPE = "application/vnd.ronin.semantic-model+json"
DASHBOARD_MEDIA_TYPE = "application/vnd.ronin.semantic-dashboard+json"


class SemanticBundleStore(Protocol):
    def list_models(self, project_id: str) -> tuple[SemanticModel, ...]: ...
    def list_dashboards(self, project_id: str) -> tuple[DashboardDefinition, ...]: ...
    def put_model(self, project_id: str, model: SemanticModel) -> SemanticModel: ...
    def put_dashboard(
        self, project_id: str, dashboard: DashboardDefinition
    ) -> DashboardDefinition: ...


@dataclass(frozen=True, slots=True)
class SemanticBundleImportPlan:
    inventory: BundleInventory
    models: tuple[SemanticModel, ...]
    dashboards: tuple[DashboardDefinition, ...]


def _path(kind: str, identifier: str) -> str:
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
    return f"objects/semantic/{kind}/{digest}.json"


def build_semantic_bundle(
    project_id: str, store: SemanticBundleStore
) -> tuple[BundleInventory, tuple[BundleFile, ...]]:
    models = tuple(sorted(store.list_models(project_id), key=lambda item: item.id))
    dashboards = tuple(sorted(store.list_dashboards(project_id), key=lambda item: item.id))
    objects: list[BundleInventoryObject] = []
    files: list[BundleFile] = []
    for kind, values, media_type in (
        ("model", models, MODEL_MEDIA_TYPE),
        ("dashboard", dashboards, DASHBOARD_MEDIA_TYPE),
    ):
        for value in values:
            logical_ref = f"semantic-{kind}:{project_id}/{value.id}"
            path = _path(kind, logical_ref)
            objects.append(BundleInventoryObject(kind, logical_ref, path))
            files.append(BundleFile(path, media_type, value.to_json().encode("utf-8")))
    inventory = BundleInventory(tuple(objects))
    inventory_file = BundleFile(
        BUNDLE_INVENTORY_PATH, INVENTORY_MEDIA_TYPE, encode_canonical_json(inventory.to_payload())
    )
    return inventory, tuple(sorted((inventory_file, *files), key=lambda item: item.path))


def export_semantic_bundle(
    project_id: str, store: SemanticBundleStore, path: Path
) -> RoninBundleManifest:
    return write_bundle(path, build_semantic_bundle(project_id, store)[1])


def plan_semantic_bundle_import(path: Path) -> SemanticBundleImportPlan:
    inventory_payload = read_bundle_payload(path, BUNDLE_INVENTORY_PATH)
    if inventory_payload.file.media_type != INVENTORY_MEDIA_TYPE:
        raise ValueError("semantic Bundle inventory has unsupported media type")
    inventory = BundleInventory.from_payload(json.loads(inventory_payload.file.data))
    models: list[SemanticModel] = []
    dashboards: list[DashboardDefinition] = []
    for item in inventory.objects:
        payload = read_bundle_payload(path, item.path)
        if payload.manifest != inventory_payload.manifest:
            raise ValueError("semantic Bundle changed while import plan was constructed")
        if item.kind == "model" and payload.file.media_type == MODEL_MEDIA_TYPE:
            models.append(SemanticModel.from_json(payload.file.data.decode("utf-8")))
        elif item.kind == "dashboard" and payload.file.media_type == DASHBOARD_MEDIA_TYPE:
            dashboards.append(DashboardDefinition.from_payload(json.loads(payload.file.data)))
        else:
            raise ValueError("unsupported semantic Bundle object")
    return SemanticBundleImportPlan(inventory, tuple(models), tuple(dashboards))


def commit_semantic_bundle_import(
    path: Path, project_id: str, store: SemanticBundleStore
) -> SemanticBundleImportPlan:
    plan = plan_semantic_bundle_import(path)
    existing_models = {item.id: item for item in store.list_models(project_id)}
    existing_dashboards = {item.id: item for item in store.list_dashboards(project_id)}
    for model in plan.models:
        if model.id in existing_models and existing_models[model.id] != model:
            raise ValueError(f"semantic model conflicts with existing definition: {model.id}")
    for dashboard in plan.dashboards:
        if dashboard.id in existing_dashboards and existing_dashboards[dashboard.id] != dashboard:
            raise ValueError(
                f"semantic dashboard conflicts with existing definition: {dashboard.id}"
            )
    for model in plan.models:
        store.put_model(project_id, model)
    for dashboard in plan.dashboards:
        store.put_dashboard(project_id, dashboard)
    return plan


__all__ = (
    "SemanticBundleImportPlan",
    "build_semantic_bundle",
    "commit_semantic_bundle_import",
    "export_semantic_bundle",
    "plan_semantic_bundle_import",
)
