"""Provider-neutral atomic commit port for supported multi-object Ronin Bundles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from studio_core import ConnectionDefinition, ProjectManifest, WorkspaceId
from studio_core.environments import ProjectEnvironmentBindings
from studio_orchestrator import Instant

from .ports import ConnectionStore, WorkspaceStore


class MultiObjectBundleImportConflict(RuntimeError):
    """Raised when target state conflicts with an atomic multi-object import."""


@dataclass(frozen=True, slots=True)
class MultiObjectBundleImportCommit:
    connections_created: int
    projects_created: int
    bindings_created: int


@runtime_checkable
class MultiObjectBundleImportStore(WorkspaceStore, ConnectionStore, Protocol):
    """Metadata boundary that commits all supported staged Bundle objects atomically."""

    def commit_multi_object_import(
        self,
        workspace_id: WorkspaceId,
        connections: tuple[ConnectionDefinition, ...],
        projects: tuple[ProjectManifest, ...],
        bindings: tuple[ProjectEnvironmentBindings, ...],
        *,
        now: Instant | str,
    ) -> MultiObjectBundleImportCommit: ...


__all__ = (
    "MultiObjectBundleImportCommit",
    "MultiObjectBundleImportConflict",
    "MultiObjectBundleImportStore",
)
