"""Provider-neutral atomic commit port for native project Bundle imports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from studio_core import ProjectManifest, WorkspaceId
from studio_core.environments import ProjectEnvironmentBindings
from studio_orchestrator import Instant

from .ports import WorkspaceStore


class ProjectBundleImportConflict(RuntimeError):
    """Raised when target state conflicts with an atomic native import commit."""


@dataclass(frozen=True, slots=True)
class ProjectBundleImportCommit:
    project_created: bool
    bindings_created: bool


@runtime_checkable
class ProjectBundleImportStore(WorkspaceStore, Protocol):
    """Workspace boundary that can atomically commit project plus deployment bindings."""

    def commit_project_import(
        self,
        workspace_id: WorkspaceId,
        project: ProjectManifest,
        bindings: ProjectEnvironmentBindings | None,
        *,
        now: Instant | str,
    ) -> ProjectBundleImportCommit: ...


__all__ = (
    "ProjectBundleImportCommit",
    "ProjectBundleImportConflict",
    "ProjectBundleImportStore",
)
