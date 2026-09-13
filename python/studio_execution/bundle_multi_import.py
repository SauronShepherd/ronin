"""Read-only staged import planning for multi-object native Ronin Bundles."""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

from studio_core import ConnectionDefinition, ProjectManifest, WorkspaceId
from studio_core.bundle_inventory import BUNDLE_INVENTORY_PATH, BundleInventory, BundleInventoryObject
from studio_core.portability import BindingRequest, RoninBundleManifest
from studio_storage.bundle import BundleIntegrityError, BundleReadLimits
from studio_storage.bundle_payload import read_bundle_payload
from studio_storage.ports import ConnectionStore, WorkspaceStore

from .bundle_connection import CONNECTION_BUNDLE_MEDIA_TYPE
from .bundle_import import BundleImportTargetError
from .bundle_inventory import INVENTORY_MEDIA_TYPE, PROJECT_BUNDLE_MEDIA_TYPE

StagedDisposition: TypeAlias = Literal["create", "noop", "existing", "collision"]
StagedPayload: TypeAlias = ProjectManifest | ConnectionDefinition


class UnsupportedMultiObjectBundle(ValueError):
    """Raised when a multi-object Bundle cannot be interpreted without semantic loss."""


@dataclass(frozen=True, slots=True)
class StagedBundleObject:
    kind: str
    logical_ref: str
    dependencies: tuple[str, ...]
    payload_digest: str
    payload: StagedPayload
    disposition: StagedDisposition
    unresolved_bindings: tuple[BindingRequest, ...]
    collision_reason: str | None = None

    def __post_init__(self) -> None:
        if self.disposition == "collision":
            if self.collision_reason is None:
                raise ValueError("collision staged object requires a reason")
        elif self.collision_reason is not None:
            raise ValueError("non-collision staged object cannot include a collision reason")
        object.__setattr__(self, "unresolved_bindings", tuple(sorted(self.unresolved_bindings)))


@dataclass(frozen=True, slots=True)
class MultiObjectBundleImportPlan:
    bundle_manifest_digest: str
    inventory_digest: str
    objects: tuple[StagedBundleObject, ...]

    @property
    def has_collisions(self) -> bool:
        return any(item.disposition == "collision" for item in self.objects)

    @property
    def unresolved_bindings(self) -> tuple[BindingRequest, ...]:
        requests = [request for item in self.objects for request in item.unresolved_bindings]
        return tuple(sorted(set(requests)))


def _require_active_workspace(store: WorkspaceStore, workspace_id: WorkspaceId) -> None:
    workspace = store.get_workspace(workspace_id)
    if workspace is None:
        raise BundleImportTargetError("target workspace does not exist")
    if workspace.archived:
        raise BundleImportTargetError("target workspace is archived")


def _ordered_inventory_objects(
    inventory: BundleInventory,
) -> tuple[BundleInventoryObject, ...]:
    by_ref = {item.logical_ref: item for item in inventory.objects}
    indegree = {item.logical_ref: len(item.dependencies) for item in inventory.objects}
    dependents: dict[str, list[str]] = {ref: [] for ref in by_ref}
    for item in inventory.objects:
        for dependency in item.dependencies:
            dependents[dependency].append(item.logical_ref)
    ready = [ref for ref, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    ordered: list[BundleInventoryObject] = []
    while ready:
        logical_ref = heapq.heappop(ready)
        ordered.append(by_ref[logical_ref])
        for dependent in sorted(dependents[logical_ref]):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                heapq.heappush(ready, dependent)
    if len(ordered) != len(inventory.objects):
        raise UnsupportedMultiObjectBundle("Bundle semantic inventory dependency graph is cyclic")
    return tuple(ordered)


def _manifest_entry_digest(manifest: RoninBundleManifest, path: str) -> str:
    for entry in manifest.entries:
        if entry.path == path:
            return entry.digest
    raise BundleIntegrityError("semantic inventory references a payload absent from manifest")


def _project_binding_requests(manifest: ProjectManifest) -> tuple[BindingRequest, ...]:
    runtime = manifest.project.execution.runtime
    if runtime is None:
        return ()
    return (
        BindingRequest(
            "runtime",
            f"runtime-profile:{runtime.adapter_id}/{runtime.profile_id}",
            required=True,
        ),
    )


def _connection_binding_requests(
    definition: ConnectionDefinition,
) -> tuple[BindingRequest, ...]:
    refs = sorted({str(ref) for _key, ref in definition.secret_refs})
    return tuple(BindingRequest("secret", ref, required=True) for ref in refs)


def _connection_shape(definition: ConnectionDefinition) -> tuple[object, ...]:
    return (
        definition.id,
        definition.name,
        definition.connector_id,
        definition.options,
        tuple(key for key, _ref in definition.secret_refs),
    )


def _stage_project(
    item: BundleInventoryObject,
    payload: bytes,
    workspace_store: WorkspaceStore,
    workspace_id: WorkspaceId,
    payload_digest: str,
) -> StagedBundleObject:
    try:
        manifest = ProjectManifest.from_json(payload.decode("utf-8"))
    except (UnicodeDecodeError, TypeError, ValueError) as exc:
        raise UnsupportedMultiObjectBundle("project Bundle payload is invalid") from exc
    if item.logical_ref != f"project:{manifest.project.id}":
        raise UnsupportedMultiObjectBundle(
            "project inventory logical identity does not match project payload"
        )
    expected_bindings = _project_binding_requests(manifest)
    if tuple(item.binding_requests) != expected_bindings:
        raise UnsupportedMultiObjectBundle(
            "project inventory binding requests do not match project payload"
        )
    existing = workspace_store.get_project(workspace_id, manifest.project.id)
    collision_reason: str | None
    if existing is None:
        disposition: StagedDisposition = "create"
        collision_reason = None
    elif existing == manifest:
        disposition = "noop"
        collision_reason = None
    else:
        disposition = "collision"
        collision_reason = "project id already exists with different portable content"
    return StagedBundleObject(
        "project",
        item.logical_ref,
        item.dependencies,
        payload_digest,
        manifest,
        disposition,
        item.binding_requests,
        collision_reason,
    )


def _stage_connection(
    item: BundleInventoryObject,
    payload: bytes,
    connection_store: ConnectionStore,
    workspace_id: WorkspaceId,
    payload_digest: str,
) -> StagedBundleObject:
    try:
        definition = ConnectionDefinition.from_json(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise UnsupportedMultiObjectBundle("connection Bundle payload is invalid") from exc
    if item.logical_ref != f"connection:{definition.id}":
        raise UnsupportedMultiObjectBundle(
            "connection inventory logical identity does not match connection payload"
        )
    expected_bindings = _connection_binding_requests(definition)
    if tuple(item.binding_requests) != expected_bindings:
        raise UnsupportedMultiObjectBundle(
            "connection inventory binding requests do not match connection payload"
        )
    existing = connection_store.get_connection(workspace_id, definition.id)
    collision_reason: str | None
    if existing is None:
        disposition: StagedDisposition = "create"
        collision_reason = None
    elif _connection_shape(existing) == _connection_shape(definition):
        disposition = "existing"
        collision_reason = None
    else:
        disposition = "collision"
        collision_reason = "connection id already exists with different portable structure"
    return StagedBundleObject(
        "connection",
        item.logical_ref,
        item.dependencies,
        payload_digest,
        definition,
        disposition,
        item.binding_requests,
        collision_reason,
    )


def plan_multi_object_bundle_import(
    bundle_path: Path,
    workspace_store: WorkspaceStore,
    connection_store: ConnectionStore,
    workspace_id: WorkspaceId,
    *,
    limits: BundleReadLimits = BundleReadLimits(),
    max_inventory_bytes: int = 8 * 1024 * 1024,
    max_object_bytes: int = 8 * 1024 * 1024,
) -> MultiObjectBundleImportPlan:
    """Verify, topologically order, and classify supported native Bundle objects."""

    _require_active_workspace(workspace_store, workspace_id)
    inventory_payload = read_bundle_payload(
        bundle_path,
        BUNDLE_INVENTORY_PATH,
        max_bytes=max_inventory_bytes,
        limits=limits,
    )
    if inventory_payload.file.media_type != INVENTORY_MEDIA_TYPE:
        raise UnsupportedMultiObjectBundle("Bundle inventory has unsupported media type")
    try:
        inventory = BundleInventory.from_json(inventory_payload.file.data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise UnsupportedMultiObjectBundle("Bundle semantic inventory is invalid") from exc

    staged: list[StagedBundleObject] = []
    for item in _ordered_inventory_objects(inventory):
        payload = read_bundle_payload(
            bundle_path,
            item.path,
            max_bytes=max_object_bytes,
            limits=limits,
        )
        if payload.manifest != inventory_payload.manifest:
            raise BundleIntegrityError("Bundle changed while staged import plan was constructed")
        digest = _manifest_entry_digest(inventory_payload.manifest, item.path)
        if item.kind == "project":
            if payload.file.media_type != PROJECT_BUNDLE_MEDIA_TYPE:
                raise UnsupportedMultiObjectBundle("project object has unsupported media type")
            staged.append(
                _stage_project(
                    item,
                    payload.file.data,
                    workspace_store,
                    workspace_id,
                    digest,
                )
            )
        elif item.kind == "connection":
            if payload.file.media_type != CONNECTION_BUNDLE_MEDIA_TYPE:
                raise UnsupportedMultiObjectBundle("connection object has unsupported media type")
            staged.append(
                _stage_connection(
                    item,
                    payload.file.data,
                    connection_store,
                    workspace_id,
                    digest,
                )
            )
        else:
            raise UnsupportedMultiObjectBundle(
                f"unsupported native Bundle object kind: {item.kind}"
            )

    return MultiObjectBundleImportPlan(
        inventory_payload.manifest.digest,
        inventory.digest,
        tuple(staged),
    )


__all__ = (
    "MultiObjectBundleImportPlan",
    "StagedBundleObject",
    "StagedDisposition",
    "UnsupportedMultiObjectBundle",
    "plan_multi_object_bundle_import",
)
