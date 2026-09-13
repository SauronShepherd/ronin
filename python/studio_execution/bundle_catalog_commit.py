"""Atomic commit application service for native catalog Bundle subgraphs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from studio_core import AssetRevision, CatalogAsset, LineageEdge, WorkspaceId
from studio_orchestrator import Instant
from studio_storage.bundle import BundleReadLimits
from studio_storage.bundle_catalog_import_port import (
    CatalogBundleImportCommit,
    CatalogBundleImportConflict,
    CatalogBundleImportStore,
)

from .bundle_catalog import CatalogBundleImportPlan, plan_catalog_bundle_import


@dataclass(frozen=True, slots=True)
class CatalogBundleImportOutcome:
    plan: CatalogBundleImportPlan
    commit: CatalogBundleImportCommit


def commit_catalog_bundle_import(
    bundle_path: Path,
    store: CatalogBundleImportStore,
    workspace_id: WorkspaceId,
    *,
    now: Instant | str,
    limits: BundleReadLimits = BundleReadLimits(),
    max_inventory_bytes: int = 8 * 1024 * 1024,
    max_object_bytes: int = 8 * 1024 * 1024,
) -> CatalogBundleImportOutcome:
    """Re-plan verified bytes, then atomically commit the selected catalog subgraph."""

    plan = plan_catalog_bundle_import(
        bundle_path,
        store,
        store,
        workspace_id,
        limits=limits,
        max_inventory_bytes=max_inventory_bytes,
        max_object_bytes=max_object_bytes,
    )
    collisions = [item for item in plan.objects if item.disposition == "collision"]
    if collisions:
        raise CatalogBundleImportConflict(
            collisions[0].collision_reason or "catalog Bundle import collision"
        )

    assets: list[CatalogAsset] = []
    revisions: list[AssetRevision] = []
    lineage: list[LineageEdge] = []
    for item in plan.objects:
        if item.kind == "catalog_asset":
            if not isinstance(item.payload, CatalogAsset):
                raise TypeError("staged catalog asset payload has unexpected type")
            assets.append(item.payload)
        elif item.kind == "catalog_revision":
            if not isinstance(item.payload, AssetRevision):
                raise TypeError("staged catalog revision payload has unexpected type")
            revisions.append(item.payload)
        elif item.kind == "catalog_lineage":
            if not isinstance(item.payload, LineageEdge):
                raise TypeError("staged catalog lineage payload has unexpected type")
            lineage.append(item.payload)
        else:
            raise AssertionError(f"unsupported staged catalog object kind: {item.kind}")

    commit = store.commit_catalog_import(
        workspace_id,
        tuple(assets),
        tuple(revisions),
        tuple(lineage),
        now=now,
    )
    return CatalogBundleImportOutcome(plan, commit)


__all__ = ("CatalogBundleImportOutcome", "commit_catalog_bundle_import")
