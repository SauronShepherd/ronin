"""Provider-neutral atomic commit port for native catalog Bundle imports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from studio_core import AssetRevision, CatalogAsset, LineageEdge, WorkspaceId
from studio_orchestrator import Instant

from .ports import CatalogStore, WorkspaceStore


class CatalogBundleImportConflict(RuntimeError):
    """Raised when target catalog state conflicts with an atomic Bundle import."""


@dataclass(frozen=True, slots=True)
class CatalogBundleImportCommit:
    assets_created: int
    revisions_created: int
    lineage_created: int


@runtime_checkable
class CatalogBundleImportStore(WorkspaceStore, CatalogStore, Protocol):
    """Catalog boundary that atomically commits one verified selected subgraph."""

    def commit_catalog_import(
        self,
        workspace_id: WorkspaceId,
        assets: tuple[CatalogAsset, ...],
        revisions: tuple[AssetRevision, ...],
        lineage: tuple[LineageEdge, ...],
        *,
        now: Instant | str,
    ) -> CatalogBundleImportCommit: ...


__all__ = (
    "CatalogBundleImportCommit",
    "CatalogBundleImportConflict",
    "CatalogBundleImportStore",
)
