"""Provider-neutral application services for workspace and project lifecycle."""

from __future__ import annotations

from dataclasses import replace

from studio_core import ProjectId, ProjectManifest, Workspace, WorkspaceId
from studio_orchestrator import Instant
from studio_storage.ports import WorkspaceStore


class WorkspaceServiceError(RuntimeError):
    """Base class for stable workspace/project application-service failures."""


class WorkspaceServiceNotFound(WorkspaceServiceError, KeyError):
    """Raised when a requested workspace or project does not exist."""


class WorkspaceServiceConflict(WorkspaceServiceError):
    """Raised when a lifecycle mutation conflicts with current durable intent."""


class WorkspaceService:
    """Application boundary for provider-neutral workspace lifecycle operations."""

    def __init__(self, store: WorkspaceStore) -> None:
        self._store = store

    def create(self, workspace: Workspace, *, now: Instant | str) -> Workspace:
        existing = self._store.get_workspace(workspace.id)
        if existing is not None:
            if existing == workspace:
                return existing
            raise WorkspaceServiceConflict(f"workspace id already exists: {workspace.id}")
        return self._store.create_workspace(workspace, now=now)

    def get(self, workspace_id: WorkspaceId) -> Workspace:
        workspace = self._store.get_workspace(workspace_id)
        if workspace is None:
            raise WorkspaceServiceNotFound(f"workspace not found: {workspace_id}")
        return workspace

    def list(self) -> tuple[Workspace, ...]:
        return self._store.list_workspaces()

    def update(
        self,
        workspace_id: WorkspaceId,
        *,
        name: str,
        description: str | None,
        now: Instant | str,
    ) -> Workspace:
        current = self.get(workspace_id)
        if current.archived:
            raise WorkspaceServiceConflict("archived workspace cannot be edited")
        updated = Workspace(workspace_id, name, description, "active")
        if updated == current:
            return current
        return self._store.update_workspace(updated, now=now)

    def archive(self, workspace_id: WorkspaceId, *, now: Instant | str) -> Workspace:
        current = self.get(workspace_id)
        if current.archived:
            return current
        archived = replace(current, state="archived")
        return self._store.update_workspace(archived, now=now)


class ProjectService:
    """Application boundary for portable project registration inside one workspace."""

    def __init__(self, store: WorkspaceStore) -> None:
        self._store = store

    def _workspace(self, workspace_id: WorkspaceId, *, mutable: bool) -> Workspace:
        workspace = self._store.get_workspace(workspace_id)
        if workspace is None:
            raise WorkspaceServiceNotFound(f"workspace not found: {workspace_id}")
        if mutable and workspace.archived:
            raise WorkspaceServiceConflict("cannot mutate projects in an archived workspace")
        return workspace

    def register(
        self,
        workspace_id: WorkspaceId,
        manifest: ProjectManifest,
        *,
        now: Instant | str,
    ) -> ProjectManifest:
        self._workspace(workspace_id, mutable=True)
        project_id = manifest.project.id
        existing = self._store.get_project(workspace_id, project_id)
        if existing is not None:
            if existing == manifest:
                return existing
            raise WorkspaceServiceConflict(
                f"project registration already exists with different intent: {project_id}"
            )
        return self._store.register_project(workspace_id, manifest, now=now)

    def get(self, workspace_id: WorkspaceId, project_id: ProjectId) -> ProjectManifest:
        self._workspace(workspace_id, mutable=False)
        manifest = self._store.get_project(workspace_id, project_id)
        if manifest is None:
            raise WorkspaceServiceNotFound(f"project not found: {workspace_id}/{project_id}")
        return manifest

    def list(self, workspace_id: WorkspaceId) -> tuple[ProjectManifest, ...]:
        self._workspace(workspace_id, mutable=False)
        return self._store.list_projects(workspace_id)

    def replace(
        self,
        workspace_id: WorkspaceId,
        manifest: ProjectManifest,
        *,
        now: Instant | str,
    ) -> ProjectManifest:
        self._workspace(workspace_id, mutable=True)
        project_id = manifest.project.id
        existing = self._store.get_project(workspace_id, project_id)
        if existing is None:
            raise WorkspaceServiceNotFound(f"project not found: {workspace_id}/{project_id}")
        if existing == manifest:
            return existing
        return self._store.replace_project(workspace_id, manifest, now=now)

    def archive(
        self, workspace_id: WorkspaceId, project_id: ProjectId, *, now: Instant | str
    ) -> bool:
        self._workspace(workspace_id, mutable=True)
        if self._store.get_project(workspace_id, project_id) is None:
            raise WorkspaceServiceNotFound(f"project not found: {workspace_id}/{project_id}")
        if not self._store.archive_project(workspace_id, project_id, now=now):
            raise WorkspaceServiceNotFound(f"project not found: {workspace_id}/{project_id}")
        return True

    def unregister(self, workspace_id: WorkspaceId, project_id: ProjectId) -> None:
        self._workspace(workspace_id, mutable=True)
        if self._store.get_project(workspace_id, project_id) is None:
            raise WorkspaceServiceNotFound(f"project not found: {workspace_id}/{project_id}")
        if not self._store.unregister_project(workspace_id, project_id):
            raise WorkspaceServiceNotFound(f"project not found: {workspace_id}/{project_id}")


__all__ = (
    "ProjectService",
    "WorkspaceService",
    "WorkspaceServiceConflict",
    "WorkspaceServiceError",
    "WorkspaceServiceNotFound",
)
