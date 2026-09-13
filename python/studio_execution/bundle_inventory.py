"""Native Ronin Bundle inventory/export for portable project intent."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from studio_core import ProjectId, WorkspaceId
from studio_core.bundle_inventory import (
    BUNDLE_INVENTORY_PATH,
    BundleInventory,
    BundleInventoryObject,
)
from studio_core.portability import BindingRequest, RoninBundleManifest
from studio_storage.bundle import BundleFile, write_bundle
from studio_storage.ports import WorkspaceStore

PROJECT_BUNDLE_MEDIA_TYPE = "application/vnd.ronin.project+json"
INVENTORY_MEDIA_TYPE = "application/vnd.ronin.bundle-inventory+json"


@dataclass(frozen=True, slots=True)
class ProjectBundleInventory:
    inventory: BundleInventory
    files: tuple[BundleFile, ...]

    def __post_init__(self) -> None:
        paths = {item.path for item in self.files}
        expected = {BUNDLE_INVENTORY_PATH, *(item.path for item in self.inventory.objects)}
        if paths != expected:
            raise ValueError("project bundle files must exactly match semantic inventory paths")


def _project_logical_ref(project_id: ProjectId) -> str:
    return f"project:{project_id}"


def _project_payload_path(logical_ref: str) -> str:
    digest = hashlib.sha256(logical_ref.encode("utf-8")).hexdigest()
    return f"objects/project/{digest}.json"


def _runtime_binding_request(manifest) -> tuple[BindingRequest, ...]:
    runtime = manifest.project.execution.runtime
    if runtime is None:
        return ()
    source_ref = f"runtime-profile:{runtime.adapter_id}/{runtime.profile_id}"
    return (BindingRequest("runtime", source_ref, required=True),)


def build_project_bundle_inventory(
    store: WorkspaceStore,
    workspace_id: WorkspaceId,
    project_id: ProjectId,
) -> ProjectBundleInventory:
    """Build deterministic portable files for one registered Ronin project."""

    manifest = store.get_project(workspace_id, project_id)
    if manifest is None:
        raise KeyError(str(project_id))
    logical_ref = _project_logical_ref(project_id)
    object_path = _project_payload_path(logical_ref)
    inventory = BundleInventory(
        (
            BundleInventoryObject(
                kind="project",
                logical_ref=logical_ref,
                path=object_path,
                binding_requests=_runtime_binding_request(manifest),
            ),
        )
    )
    files = (
        BundleFile(
            BUNDLE_INVENTORY_PATH,
            INVENTORY_MEDIA_TYPE,
            inventory.to_json().encode("utf-8"),
        ),
        BundleFile(
            object_path,
            PROJECT_BUNDLE_MEDIA_TYPE,
            manifest.to_json().encode("utf-8"),
        ),
    )
    return ProjectBundleInventory(inventory, tuple(sorted(files, key=lambda item: item.path)))


def export_project_bundle(
    store: WorkspaceStore,
    workspace_id: WorkspaceId,
    project_id: ProjectId,
    path: Path,
) -> RoninBundleManifest:
    """Write a deterministic native project bundle using the shared archive adapter."""

    built = build_project_bundle_inventory(store, workspace_id, project_id)
    return write_bundle(path, built.files)


__all__ = (
    "INVENTORY_MEDIA_TYPE",
    "PROJECT_BUNDLE_MEDIA_TYPE",
    "ProjectBundleInventory",
    "build_project_bundle_inventory",
    "export_project_bundle",
)
