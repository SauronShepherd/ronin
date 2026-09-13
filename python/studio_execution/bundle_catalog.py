"""Native Ronin Bundle export/planning for explicit governed catalog subgraphs."""

from __future__ import annotations

import hashlib
import heapq
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

from studio_core import (
    AssetId,
    AssetRef,
    AssetRevision,
    CatalogAsset,
    LineageEdge,
    WorkspaceId,
)
from studio_core.bundle_inventory import (
    BUNDLE_INVENTORY_PATH,
    BundleInventory,
    BundleInventoryObject,
)
from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.portability import RoninBundleManifest
from studio_storage.bundle import (
    BundleFile,
    BundleIntegrityError,
    BundleReadLimits,
    write_bundle,
)
from studio_storage.bundle_payload import read_bundle_payload
from studio_storage.ports import CatalogStore, WorkspaceStore

CATALOG_ASSET_MEDIA_TYPE = "application/vnd.ronin.catalog-asset+json"
CATALOG_REVISION_MEDIA_TYPE = "application/vnd.ronin.catalog-revision+json"
CATALOG_LINEAGE_MEDIA_TYPE = "application/vnd.ronin.catalog-lineage+json"
INVENTORY_MEDIA_TYPE = "application/vnd.ronin.bundle-inventory+json"

CatalogDisposition: TypeAlias = Literal["create", "noop", "collision"]
CatalogPayload: TypeAlias = CatalogAsset | AssetRevision | LineageEdge


class UnsupportedCatalogBundle(ValueError):
    """Raised when catalog Bundle semantics cannot be interpreted without loss."""


class CatalogBundleTargetError(ValueError):
    """Raised when the target workspace cannot accept catalog import planning."""


@dataclass(frozen=True, slots=True)
class CatalogBundleInventory:
    inventory: BundleInventory
    files: tuple[BundleFile, ...]

    def __post_init__(self) -> None:
        paths = tuple(file.path for file in self.files)
        if len(paths) != len(set(paths)):
            raise ValueError("catalog Bundle file paths must be unique")
        expected = {
            BUNDLE_INVENTORY_PATH,
            *(item.path for item in self.inventory.objects),
        }
        if set(paths) != expected:
            raise ValueError(
                "catalog Bundle files must exactly match semantic inventory paths"
            )


@dataclass(frozen=True, slots=True)
class StagedCatalogObject:
    kind: str
    logical_ref: str
    dependencies: tuple[str, ...]
    payload_digest: str
    payload: CatalogPayload
    disposition: CatalogDisposition
    collision_reason: str | None = None

    def __post_init__(self) -> None:
        if self.disposition == "collision":
            if self.collision_reason is None:
                raise ValueError("catalog collision requires a reason")
        elif self.collision_reason is not None:
            raise ValueError("non-collision catalog object cannot include a reason")


@dataclass(frozen=True, slots=True)
class CatalogBundleImportPlan:
    bundle_manifest_digest: str
    inventory_digest: str
    objects: tuple[StagedCatalogObject, ...]

    @property
    def has_collisions(self) -> bool:
        return any(item.disposition == "collision" for item in self.objects)


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _asset_logical_ref(asset: CatalogAsset) -> str:
    return f"catalog-asset:{_hash_text(asset.id.value)}"


def _revision_logical_ref(revision: AssetRevision) -> str:
    digest = hashlib.sha256(
        encode_canonical_json(revision.ref.to_payload())
    ).hexdigest()
    return f"catalog-revision:{digest}"


def _lineage_logical_ref(edge: LineageEdge) -> str:
    return f"catalog-lineage:{edge.digest}"


def _payload_path(kind: str, logical_ref: str) -> str:
    digest = _hash_text(logical_ref)
    return f"objects/catalog/{kind}/{digest}.json"


def _manifest_entry_digest(manifest: RoninBundleManifest, path: str) -> str:
    for entry in manifest.entries:
        if entry.path == path:
            return entry.digest
    raise BundleIntegrityError(
        "catalog inventory references a payload absent from manifest"
    )


def _require_active_workspace(
    store: WorkspaceStore,
    workspace_id: WorkspaceId,
) -> None:
    workspace = store.get_workspace(workspace_id)
    if workspace is None:
        raise CatalogBundleTargetError("target workspace does not exist")
    if workspace.archived:
        raise CatalogBundleTargetError("target workspace is archived")


def _selected_catalog(
    store: CatalogStore,
    workspace_id: WorkspaceId,
    refs: tuple[AssetRef, ...],
) -> tuple[
    tuple[CatalogAsset, ...],
    tuple[AssetRevision, ...],
    tuple[LineageEdge, ...],
]:
    if not refs:
        raise ValueError("catalog Bundle selection must include at least one revision")
    canonical_refs = tuple(sorted(refs))
    if len(canonical_refs) != len(set(canonical_refs)):
        raise ValueError("catalog Bundle selected revisions must be unique")

    assets_by_id: dict[AssetId, CatalogAsset] = {}
    revisions: list[AssetRevision] = []
    for ref in canonical_refs:
        asset = store.get_asset(workspace_id, ref.asset_id)
        if asset is None:
            raise KeyError(str(ref.asset_id))
        revision = store.get_revision(workspace_id, ref)
        if revision is None:
            raise KeyError(f"{ref.asset_id}@{ref.version}")
        assets_by_id[asset.id] = asset
        revisions.append(revision)

    selected = set(canonical_refs)
    lineage_by_digest: dict[str, LineageEdge] = {}
    for ref in canonical_refs:
        for edge in store.downstream(workspace_id, ref):
            if edge.source in selected and edge.target in selected:
                lineage_by_digest[edge.digest] = edge
    assets = tuple(sorted(assets_by_id.values(), key=lambda item: str(item.id)))
    lineage = tuple(lineage_by_digest[key] for key in sorted(lineage_by_digest))
    return assets, tuple(revisions), lineage


def build_catalog_bundle_inventory(
    store: CatalogStore,
    workspace_id: WorkspaceId,
    refs: tuple[AssetRef, ...],
) -> CatalogBundleInventory:
    """Build deterministic portable files for an explicit revision/lineage subgraph."""

    assets, revisions, lineage = _selected_catalog(store, workspace_id, refs)
    asset_refs = {asset.id: _asset_logical_ref(asset) for asset in assets}
    revision_refs = {
        revision.ref: _revision_logical_ref(revision) for revision in revisions
    }
    objects: list[BundleInventoryObject] = []
    payloads: list[BundleFile] = []

    for asset in assets:
        logical_ref = asset_refs[asset.id]
        path = _payload_path("asset", logical_ref)
        objects.append(BundleInventoryObject("catalog_asset", logical_ref, path))
        payloads.append(
            BundleFile(
                path,
                CATALOG_ASSET_MEDIA_TYPE,
                asset.to_json().encode("utf-8"),
            )
        )

    for revision in revisions:
        logical_ref = revision_refs[revision.ref]
        path = _payload_path("revision", logical_ref)
        objects.append(
            BundleInventoryObject(
                "catalog_revision",
                logical_ref,
                path,
                dependencies=(asset_refs[revision.ref.asset_id],),
            )
        )
        payloads.append(
            BundleFile(
                path,
                CATALOG_REVISION_MEDIA_TYPE,
                revision.to_json().encode("utf-8"),
            )
        )

    for edge in lineage:
        logical_ref = _lineage_logical_ref(edge)
        path = _payload_path("lineage", logical_ref)
        objects.append(
            BundleInventoryObject(
                "catalog_lineage",
                logical_ref,
                path,
                dependencies=(
                    revision_refs[edge.source],
                    revision_refs[edge.target],
                ),
            )
        )
        payloads.append(
            BundleFile(
                path,
                CATALOG_LINEAGE_MEDIA_TYPE,
                edge.to_json().encode("utf-8"),
            )
        )

    inventory = BundleInventory(tuple(objects))
    files = [
        BundleFile(
            BUNDLE_INVENTORY_PATH,
            INVENTORY_MEDIA_TYPE,
            inventory.to_json().encode("utf-8"),
        ),
        *payloads,
    ]
    return CatalogBundleInventory(
        inventory,
        tuple(sorted(files, key=lambda item: item.path)),
    )


def export_catalog_bundle(
    store: CatalogStore,
    workspace_id: WorkspaceId,
    refs: tuple[AssetRef, ...],
    path: Path,
) -> RoninBundleManifest:
    """Write a deterministic Bundle for an explicit governed catalog subgraph."""

    built = build_catalog_bundle_inventory(store, workspace_id, refs)
    return write_bundle(path, built.files)


def _ordered_objects(
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
        raise UnsupportedCatalogBundle("catalog Bundle dependency graph is cyclic")
    return tuple(ordered)


def _stage_asset(
    item: BundleInventoryObject,
    data: bytes,
    store: CatalogStore,
    workspace_id: WorkspaceId,
    digest: str,
) -> StagedCatalogObject:
    if item.dependencies or item.binding_requests:
        raise UnsupportedCatalogBundle("catalog asset inventory semantics are invalid")
    try:
        asset = CatalogAsset.from_json(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise UnsupportedCatalogBundle("catalog asset payload is invalid") from exc
    if item.logical_ref != _asset_logical_ref(asset):
        raise UnsupportedCatalogBundle(
            "catalog asset logical identity does not match payload"
        )
    existing = store.get_asset(workspace_id, asset.id)
    if existing is None:
        disposition: CatalogDisposition = "create"
        reason = None
    elif existing == asset:
        disposition = "noop"
        reason = None
    else:
        disposition = "collision"
        reason = "catalog asset id already exists with different content"
    return StagedCatalogObject(
        "catalog_asset",
        item.logical_ref,
        item.dependencies,
        digest,
        asset,
        disposition,
        reason,
    )


def _stage_revision(
    item: BundleInventoryObject,
    data: bytes,
    store: CatalogStore,
    workspace_id: WorkspaceId,
    digest: str,
    known_assets: dict[AssetId, str],
) -> StagedCatalogObject:
    if item.binding_requests:
        raise UnsupportedCatalogBundle(
            "catalog revision must not request deployment bindings"
        )
    try:
        revision = AssetRevision.from_json(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise UnsupportedCatalogBundle("catalog revision payload is invalid") from exc
    expected_dependency = known_assets.get(revision.ref.asset_id)
    if expected_dependency is None or item.dependencies != (expected_dependency,):
        raise UnsupportedCatalogBundle(
            "catalog revision dependency does not match asset payload"
        )
    if item.logical_ref != _revision_logical_ref(revision):
        raise UnsupportedCatalogBundle(
            "catalog revision logical identity does not match payload"
        )
    existing = store.get_revision(workspace_id, revision.ref)
    if existing is None:
        disposition: CatalogDisposition = "create"
        reason = None
    elif existing == revision:
        disposition = "noop"
        reason = None
    else:
        disposition = "collision"
        reason = "catalog asset version already exists with different revision metadata"
    return StagedCatalogObject(
        "catalog_revision",
        item.logical_ref,
        item.dependencies,
        digest,
        revision,
        disposition,
        reason,
    )


def _stage_lineage(
    item: BundleInventoryObject,
    data: bytes,
    store: CatalogStore,
    workspace_id: WorkspaceId,
    digest: str,
    known_revisions: dict[AssetRef, str],
) -> StagedCatalogObject:
    if item.binding_requests:
        raise UnsupportedCatalogBundle(
            "catalog lineage must not request deployment bindings"
        )
    try:
        edge = LineageEdge.from_json(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise UnsupportedCatalogBundle("catalog lineage payload is invalid") from exc
    source_dependency = known_revisions.get(edge.source)
    target_dependency = known_revisions.get(edge.target)
    if source_dependency is None or target_dependency is None:
        raise UnsupportedCatalogBundle(
            "catalog lineage references a revision absent from the staged subgraph"
        )
    expected = tuple(sorted((source_dependency, target_dependency)))
    if item.dependencies != expected:
        raise UnsupportedCatalogBundle(
            "catalog lineage dependencies do not match payload revisions"
        )
    if item.logical_ref != _lineage_logical_ref(edge):
        raise UnsupportedCatalogBundle(
            "catalog lineage logical identity does not match payload"
        )
    existing = next(
        (
            candidate
            for candidate in store.upstream(workspace_id, edge.target)
            if candidate.digest == edge.digest
        ),
        None,
    )
    disposition: CatalogDisposition = "noop" if existing == edge else "create"
    return StagedCatalogObject(
        "catalog_lineage",
        item.logical_ref,
        item.dependencies,
        digest,
        edge,
        disposition,
    )


def plan_catalog_bundle_import(
    bundle_path: Path,
    workspace_store: WorkspaceStore,
    catalog_store: CatalogStore,
    workspace_id: WorkspaceId,
    *,
    limits: BundleReadLimits = BundleReadLimits(),
    max_inventory_bytes: int = 8 * 1024 * 1024,
    max_object_bytes: int = 8 * 1024 * 1024,
) -> CatalogBundleImportPlan:
    """Verify and classify one selected catalog subgraph without mutating target state."""

    _require_active_workspace(workspace_store, workspace_id)
    inventory_payload = read_bundle_payload(
        bundle_path,
        BUNDLE_INVENTORY_PATH,
        max_bytes=max_inventory_bytes,
        limits=limits,
    )
    if inventory_payload.file.media_type != INVENTORY_MEDIA_TYPE:
        raise UnsupportedCatalogBundle(
            "catalog Bundle inventory has unsupported media type"
        )
    try:
        inventory = BundleInventory.from_json(
            inventory_payload.file.data.decode("utf-8")
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise UnsupportedCatalogBundle("catalog Bundle inventory is invalid") from exc

    staged: list[StagedCatalogObject] = []
    known_assets: dict[AssetId, str] = {}
    known_revisions: dict[AssetRef, str] = {}
    for item in _ordered_objects(inventory):
        payload = read_bundle_payload(
            bundle_path,
            item.path,
            max_bytes=max_object_bytes,
            limits=limits,
        )
        if payload.manifest != inventory_payload.manifest:
            raise BundleIntegrityError(
                "catalog Bundle changed while import plan was constructed"
            )
        digest = _manifest_entry_digest(inventory_payload.manifest, item.path)
        if item.kind == "catalog_asset":
            if payload.file.media_type != CATALOG_ASSET_MEDIA_TYPE:
                raise UnsupportedCatalogBundle(
                    "catalog asset has unsupported media type"
                )
            staged_item = _stage_asset(
                item,
                payload.file.data,
                catalog_store,
                workspace_id,
                digest,
            )
            assert isinstance(staged_item.payload, CatalogAsset)
            known_assets[staged_item.payload.id] = staged_item.logical_ref
        elif item.kind == "catalog_revision":
            if payload.file.media_type != CATALOG_REVISION_MEDIA_TYPE:
                raise UnsupportedCatalogBundle(
                    "catalog revision has unsupported media type"
                )
            staged_item = _stage_revision(
                item,
                payload.file.data,
                catalog_store,
                workspace_id,
                digest,
                known_assets,
            )
            assert isinstance(staged_item.payload, AssetRevision)
            known_revisions[staged_item.payload.ref] = staged_item.logical_ref
        elif item.kind == "catalog_lineage":
            if payload.file.media_type != CATALOG_LINEAGE_MEDIA_TYPE:
                raise UnsupportedCatalogBundle(
                    "catalog lineage has unsupported media type"
                )
            staged_item = _stage_lineage(
                item,
                payload.file.data,
                catalog_store,
                workspace_id,
                digest,
                known_revisions,
            )
        else:
            raise UnsupportedCatalogBundle(
                f"unsupported catalog Bundle object kind: {item.kind}"
            )
        staged.append(staged_item)

    return CatalogBundleImportPlan(
        inventory_payload.manifest.digest,
        inventory.digest,
        tuple(staged),
    )


__all__ = (
    "CATALOG_ASSET_MEDIA_TYPE",
    "CATALOG_LINEAGE_MEDIA_TYPE",
    "CATALOG_REVISION_MEDIA_TYPE",
    "CatalogBundleImportPlan",
    "CatalogBundleInventory",
    "CatalogBundleTargetError",
    "StagedCatalogObject",
    "UnsupportedCatalogBundle",
    "build_catalog_bundle_inventory",
    "export_catalog_bundle",
    "plan_catalog_bundle_import",
)
