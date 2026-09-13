"""Native Ronin Bundle export, planning, and secret-remapped connection import."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

from studio_core import ConnectionDefinition, ConnectionId, SecretRef, WorkspaceId
from studio_core.bundle_inventory import (
    BUNDLE_INVENTORY_PATH,
    BundleInventory,
    BundleInventoryObject,
)
from studio_core.environments import DeploymentBinding
from studio_core.portability import BindingRequest, RoninBundleManifest
from studio_orchestrator import Instant
from studio_storage.bundle import BundleFile, BundleIntegrityError, BundleReadLimits, write_bundle
from studio_storage.bundle_payload import read_bundle_payload
from studio_storage.ports import ConnectionStore, WorkspaceStore

CONNECTION_BUNDLE_MEDIA_TYPE = "application/vnd.ronin.connection+json"
INVENTORY_MEDIA_TYPE = "application/vnd.ronin.bundle-inventory+json"

ConnectionImportDisposition: TypeAlias = Literal["create", "existing", "collision"]
_CONNECTION_IMPORT_DISPOSITIONS = frozenset({"create", "existing", "collision"})


class UnsupportedConnectionBundle(ValueError):
    """Raised when the native connection importer cannot interpret the semantic bundle."""


class ConnectionBundleBindingError(ValueError):
    """Raised when secret remaps do not exactly satisfy the Bundle binding requests."""


class ConnectionBundleImportConflict(RuntimeError):
    """Raised when target connection structure conflicts with the portable definition."""


@dataclass(frozen=True, slots=True)
class ConnectionBundleInventory:
    inventory: BundleInventory
    files: tuple[BundleFile, ...]

    def __post_init__(self) -> None:
        paths = tuple(item.path for item in self.files)
        if len(paths) != len(set(paths)):
            raise ValueError("connection Bundle file paths must be unique")
        expected = {BUNDLE_INVENTORY_PATH, *(item.path for item in self.inventory.objects)}
        if set(paths) != expected:
            raise ValueError("connection Bundle files must exactly match semantic inventory paths")


@dataclass(frozen=True, slots=True)
class ConnectionBundleImportPlan:
    bundle_manifest_digest: str
    inventory_digest: str
    connection_payload_digest: str
    connection: ConnectionDefinition
    disposition: ConnectionImportDisposition
    unresolved_bindings: tuple[BindingRequest, ...] = ()
    collision_reason: str | None = None

    def __post_init__(self) -> None:
        if self.disposition not in _CONNECTION_IMPORT_DISPOSITIONS:
            raise ValueError("unsupported connection Bundle import disposition")
        bindings = tuple(sorted(self.unresolved_bindings))
        object.__setattr__(self, "unresolved_bindings", bindings)
        if self.disposition == "collision":
            if self.collision_reason is None:
                raise ValueError("collision connection import plan requires a reason")
        elif self.collision_reason is not None:
            raise ValueError("non-collision connection import plan cannot include a reason")

    @property
    def connection_id(self) -> ConnectionId:
        return self.connection.id


@dataclass(frozen=True, slots=True)
class ConnectionBundleImportOutcome:
    plan: ConnectionBundleImportPlan
    resolved_connection: ConnectionDefinition


def _logical_ref(connection_id: ConnectionId) -> str:
    return f"connection:{connection_id}"


def _payload_path(logical_ref: str) -> str:
    digest = hashlib.sha256(logical_ref.encode("utf-8")).hexdigest()
    return f"objects/connection/{digest}.json"


def _secret_binding_requests(
    definition: ConnectionDefinition,
) -> tuple[BindingRequest, ...]:
    refs = sorted({str(ref) for _key, ref in definition.secret_refs})
    return tuple(BindingRequest("secret", ref, required=True) for ref in refs)


def _portable_shape(definition: ConnectionDefinition) -> tuple[object, ...]:
    """Connection semantics excluding deployment-remappable secret URI targets."""

    return (
        definition.id,
        definition.name,
        definition.connector_id,
        definition.options,
        tuple(key for key, _ref in definition.secret_refs),
    )


def _manifest_entry_digest(manifest: RoninBundleManifest, path: str) -> str:
    for entry in manifest.entries:
        if entry.path == path:
            return entry.digest
    raise BundleIntegrityError("connection inventory references a payload absent from manifest")


def _require_active_workspace(store: WorkspaceStore, workspace_id: WorkspaceId) -> None:
    workspace = store.get_workspace(workspace_id)
    if workspace is None:
        raise ConnectionBundleImportConflict("target workspace does not exist")
    if workspace.archived:
        raise ConnectionBundleImportConflict("target workspace is archived")


def build_connection_bundle_inventory(
    store: ConnectionStore,
    workspace_id: WorkspaceId,
    connection_id: ConnectionId,
) -> ConnectionBundleInventory:
    """Build deterministic portable files for one native connection definition."""

    definition = store.get_connection(workspace_id, connection_id)
    if definition is None:
        raise KeyError(str(connection_id))
    logical_ref = _logical_ref(connection_id)
    object_path = _payload_path(logical_ref)
    inventory = BundleInventory(
        (
            BundleInventoryObject(
                kind="connection",
                logical_ref=logical_ref,
                path=object_path,
                binding_requests=_secret_binding_requests(definition),
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
            CONNECTION_BUNDLE_MEDIA_TYPE,
            definition.to_json().encode("utf-8"),
        ),
    )
    return ConnectionBundleInventory(inventory, tuple(sorted(files, key=lambda item: item.path)))


def export_connection_bundle(
    store: ConnectionStore,
    workspace_id: WorkspaceId,
    connection_id: ConnectionId,
    path: Path,
) -> RoninBundleManifest:
    """Write one deterministic native connection Bundle."""

    built = build_connection_bundle_inventory(store, workspace_id, connection_id)
    return write_bundle(path, built.files)


def plan_connection_bundle_import(
    bundle_path: Path,
    workspace_store: WorkspaceStore,
    connection_store: ConnectionStore,
    workspace_id: WorkspaceId,
    *,
    limits: BundleReadLimits = BundleReadLimits(),
    max_inventory_bytes: int = 8 * 1024 * 1024,
    max_connection_bytes: int = 8 * 1024 * 1024,
) -> ConnectionBundleImportPlan:
    """Verify and classify one native connection Bundle without mutating target state."""

    _require_active_workspace(workspace_store, workspace_id)
    inventory_payload = read_bundle_payload(
        bundle_path,
        BUNDLE_INVENTORY_PATH,
        max_bytes=max_inventory_bytes,
        limits=limits,
    )
    if inventory_payload.file.media_type != INVENTORY_MEDIA_TYPE:
        raise UnsupportedConnectionBundle("Bundle inventory has unsupported media type")
    try:
        inventory = BundleInventory.from_json(inventory_payload.file.data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise UnsupportedConnectionBundle("Bundle semantic inventory is invalid") from exc
    if len(inventory.objects) != 1 or inventory.objects[0].kind != "connection":
        raise UnsupportedConnectionBundle(
            "native connection importer requires exactly one supported connection object"
        )
    item = inventory.objects[0]

    connection_payload = read_bundle_payload(
        bundle_path,
        item.path,
        max_bytes=max_connection_bytes,
        limits=limits,
    )
    if connection_payload.manifest != inventory_payload.manifest:
        raise BundleIntegrityError("Bundle changed while connection import plan was constructed")
    if connection_payload.file.media_type != CONNECTION_BUNDLE_MEDIA_TYPE:
        raise UnsupportedConnectionBundle("connection object has unsupported media type")
    try:
        definition = ConnectionDefinition.from_json(connection_payload.file.data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise UnsupportedConnectionBundle("connection Bundle payload is invalid") from exc
    if item.logical_ref != _logical_ref(definition.id):
        raise UnsupportedConnectionBundle(
            "connection inventory logical identity does not match connection payload"
        )

    expected_requests = _secret_binding_requests(definition)
    if tuple(item.binding_requests) != expected_requests:
        raise UnsupportedConnectionBundle(
            "connection inventory secret binding requests do not match connection payload"
        )

    existing = connection_store.get_connection(workspace_id, definition.id)
    collision_reason: str | None
    if existing is None:
        disposition: ConnectionImportDisposition = "create"
        collision_reason = None
    elif _portable_shape(existing) == _portable_shape(definition):
        disposition = "existing"
        collision_reason = None
    else:
        disposition = "collision"
        collision_reason = "connection id already exists with different portable structure"

    return ConnectionBundleImportPlan(
        bundle_manifest_digest=inventory_payload.manifest.digest,
        inventory_digest=inventory.digest,
        connection_payload_digest=_manifest_entry_digest(inventory_payload.manifest, item.path),
        connection=definition,
        disposition=disposition,
        unresolved_bindings=inventory.unresolved_bindings,
        collision_reason=collision_reason,
    )


def resolve_connection_secret_bindings(
    plan: ConnectionBundleImportPlan,
    resolutions: tuple[DeploymentBinding, ...],
) -> ConnectionDefinition:
    """Apply explicit secret-reference remaps without exposing or fabricating secret material."""

    expected = {(request.kind, request.source_ref): request for request in plan.unresolved_bindings}
    supplied: dict[tuple[str, str], DeploymentBinding] = {}
    for resolution in resolutions:
        key = (resolution.kind, resolution.source_ref)
        if key in supplied:
            raise ConnectionBundleBindingError("duplicate connection Bundle binding resolution")
        if key not in expected:
            raise ConnectionBundleBindingError("connection Bundle binding resolution was not requested")
        supplied[key] = resolution
    if any(request.required and key not in supplied for key, request in expected.items()):
        raise ConnectionBundleBindingError("required connection Bundle bindings remain unresolved")

    remapped_refs: list[tuple[str, SecretRef]] = []
    for key, source_ref in plan.connection.secret_refs:
        resolution = supplied.get(("secret", str(source_ref)))
        if resolution is None:
            remapped_refs.append((key, source_ref))
        else:
            remapped_refs.append((key, SecretRef(resolution.target_ref)))
    return ConnectionDefinition(
        id=plan.connection.id,
        name=plan.connection.name,
        connector_id=plan.connection.connector_id,
        options=plan.connection.options,
        secret_refs=tuple(remapped_refs),
    )


def commit_connection_bundle_import(
    bundle_path: Path,
    workspace_store: WorkspaceStore,
    connection_store: ConnectionStore,
    workspace_id: WorkspaceId,
    *,
    resolutions: tuple[DeploymentBinding, ...] = (),
    now: Instant | str,
    limits: BundleReadLimits = BundleReadLimits(),
    max_inventory_bytes: int = 8 * 1024 * 1024,
    max_connection_bytes: int = 8 * 1024 * 1024,
) -> ConnectionBundleImportOutcome:
    """Re-plan verified bytes, explicitly remap secrets, then create/exact-noop the target."""

    plan = plan_connection_bundle_import(
        bundle_path,
        workspace_store,
        connection_store,
        workspace_id,
        limits=limits,
        max_inventory_bytes=max_inventory_bytes,
        max_connection_bytes=max_connection_bytes,
    )
    if plan.disposition == "collision":
        raise ConnectionBundleImportConflict(plan.collision_reason or "connection import collision")
    resolved = resolve_connection_secret_bindings(plan, resolutions)
    connection_store.create_connection(workspace_id, resolved, now=now)
    return ConnectionBundleImportOutcome(plan, resolved)


__all__ = (
    "CONNECTION_BUNDLE_MEDIA_TYPE",
    "ConnectionBundleBindingError",
    "ConnectionBundleImportConflict",
    "ConnectionBundleImportOutcome",
    "ConnectionBundleImportPlan",
    "ConnectionBundleInventory",
    "ConnectionImportDisposition",
    "UnsupportedConnectionBundle",
    "build_connection_bundle_inventory",
    "commit_connection_bundle_import",
    "export_connection_bundle",
    "plan_connection_bundle_import",
    "resolve_connection_secret_bindings",
)
