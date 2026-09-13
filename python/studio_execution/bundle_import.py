"""Read-only import planning for native Ronin project bundles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

from studio_core import ProjectId, ProjectManifest, WorkspaceId
from studio_core.bundle_inventory import BUNDLE_INVENTORY_PATH, BundleInventory
from studio_core.portability import BindingRequest, RoninBundleManifest
from studio_storage.bundle import BundleIntegrityError, BundleReadLimits
from studio_storage.bundle_payload import read_bundle_payload
from studio_storage.ports import WorkspaceStore

from .bundle_inventory import INVENTORY_MEDIA_TYPE, PROJECT_BUNDLE_MEDIA_TYPE

ImportDisposition: TypeAlias = Literal["create", "noop", "collision"]
_IMPORT_DISPOSITIONS = frozenset({"create", "noop", "collision"})


class BundleImportTargetError(ValueError):
    """Raised when the requested target workspace cannot accept an import."""


class UnsupportedBundleInventory(ValueError):
    """Raised when this native importer cannot interpret every semantic object."""


@dataclass(frozen=True, slots=True)
class ProjectBundleImportPlan:
    bundle_manifest_digest: str
    inventory_digest: str
    project_payload_digest: str
    project: ProjectManifest
    disposition: ImportDisposition
    unresolved_bindings: tuple[BindingRequest, ...] = ()
    collision_reason: str | None = None

    def __post_init__(self) -> None:
        if self.disposition not in _IMPORT_DISPOSITIONS:
            raise ValueError("unsupported project Bundle import disposition")
        bindings = tuple(sorted(self.unresolved_bindings))
        object.__setattr__(self, "unresolved_bindings", bindings)
        if self.disposition == "collision":
            if self.collision_reason is None:
                raise ValueError("collision import plan requires a reason")
        elif self.collision_reason is not None:
            raise ValueError("non-collision import plan must not include a collision reason")

    @property
    def project_id(self) -> ProjectId:
        return self.project.project.id

    @property
    def has_required_bindings(self) -> bool:
        return any(request.required for request in self.unresolved_bindings)


def _manifest_entry_digest(manifest: RoninBundleManifest, path: str) -> str:
    for entry in manifest.entries:
        if entry.path == path:
            return entry.digest
    raise BundleIntegrityError("semantic inventory references a payload absent from manifest")


def _require_active_target_workspace(store: WorkspaceStore, workspace_id: WorkspaceId) -> None:
    workspace = store.get_workspace(workspace_id)
    if workspace is None:
        raise BundleImportTargetError("target workspace does not exist")
    if workspace.archived:
        raise BundleImportTargetError("target workspace is archived")


def plan_project_bundle_import(
    bundle_path: Path,
    store: WorkspaceStore,
    workspace_id: WorkspaceId,
    *,
    limits: BundleReadLimits = BundleReadLimits(),
    max_inventory_bytes: int = 8 * 1024 * 1024,
    max_project_bytes: int = 8 * 1024 * 1024,
) -> ProjectBundleImportPlan:
    """Verify and classify one native project bundle without mutating target state."""

    _require_active_target_workspace(store, workspace_id)
    inventory_payload = read_bundle_payload(
        bundle_path,
        BUNDLE_INVENTORY_PATH,
        max_bytes=max_inventory_bytes,
        limits=limits,
    )
    if inventory_payload.file.media_type != INVENTORY_MEDIA_TYPE:
        raise UnsupportedBundleInventory("bundle inventory has unsupported media type")
    try:
        inventory = BundleInventory.from_json(inventory_payload.file.data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise UnsupportedBundleInventory("bundle semantic inventory is invalid") from exc

    if len(inventory.objects) != 1 or inventory.objects[0].kind != "project":
        raise UnsupportedBundleInventory(
            "native project importer requires exactly one supported project object"
        )
    item = inventory.objects[0]

    project_payload = read_bundle_payload(
        bundle_path,
        item.path,
        max_bytes=max_project_bytes,
        limits=limits,
    )
    if project_payload.manifest != inventory_payload.manifest:
        raise BundleIntegrityError("bundle changed while import plan was being constructed")
    if project_payload.file.media_type != PROJECT_BUNDLE_MEDIA_TYPE:
        raise UnsupportedBundleInventory("project object has unsupported media type")
    try:
        project = ProjectManifest.from_json(project_payload.file.data.decode("utf-8"))
    except (UnicodeDecodeError, TypeError, ValueError) as exc:
        raise UnsupportedBundleInventory("project bundle payload is invalid") from exc

    expected_ref = f"project:{project.project.id}"
    if item.logical_ref != expected_ref:
        raise UnsupportedBundleInventory(
            "project inventory logical identity does not match project payload"
        )

    existing = store.get_project(workspace_id, project.project.id)
    collision_reason: str | None
    if existing is None:
        disposition: ImportDisposition = "create"
        collision_reason = None
    elif existing == project:
        disposition = "noop"
        collision_reason = None
    else:
        disposition = "collision"
        collision_reason = "project id already exists with different portable content"

    return ProjectBundleImportPlan(
        bundle_manifest_digest=inventory_payload.manifest.digest,
        inventory_digest=inventory.digest,
        project_payload_digest=_manifest_entry_digest(
            inventory_payload.manifest,
            item.path,
        ),
        project=project,
        disposition=disposition,
        unresolved_bindings=inventory.unresolved_bindings,
        collision_reason=collision_reason,
    )


__all__ = (
    "BundleImportTargetError",
    "ImportDisposition",
    "ProjectBundleImportPlan",
    "UnsupportedBundleInventory",
    "plan_project_bundle_import",
)
