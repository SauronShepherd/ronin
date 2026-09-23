"""Stable application ports owned by the Workspaces/Projects plugin."""

from __future__ import annotations

from typing import Protocol

from studio_core import ProjectId, ProjectManifest, Workspace, WorkspaceId


class WorkspacePort(Protocol):
    def create(self, workspace: Workspace, *, now: object) -> Workspace: ...

    def list(self) -> tuple[Workspace, ...]: ...

    def get(self, workspace_id: WorkspaceId) -> Workspace: ...

    def update(
        self,
        workspace_id: WorkspaceId,
        *,
        name: str,
        description: str | None,
        now: object,
    ) -> Workspace: ...

    def archive(self, workspace_id: WorkspaceId, *, now: object) -> Workspace: ...


class ProjectPort(Protocol):
    def register(
        self, workspace_id: WorkspaceId, manifest: ProjectManifest, *, now: object
    ) -> ProjectManifest: ...

    def list(self, workspace_id: WorkspaceId) -> tuple[ProjectManifest, ...]: ...

    def get(self, workspace_id: WorkspaceId, project_id: ProjectId) -> ProjectManifest: ...

    def replace(
        self, workspace_id: WorkspaceId, manifest: ProjectManifest, *, now: object
    ) -> ProjectManifest: ...

    def unregister(self, workspace_id: WorkspaceId, project_id: ProjectId) -> None: ...

    def archive(self, workspace_id: WorkspaceId, project_id: ProjectId, *, now: object) -> bool: ...


__all__ = ("ProjectPort", "WorkspacePort")
