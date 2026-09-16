"""Provider-neutral application services for environment and deployment bindings."""

from __future__ import annotations

from dataclasses import replace

from studio_core import ProjectId, WorkspaceId
from studio_core.environments import (
    EnvironmentDefinition,
    EnvironmentId,
    ProjectEnvironmentBindings,
)
from studio_core.workspaces import Workspace
from studio_orchestrator import Instant
from studio_storage.ports import EnvironmentStore, WorkspaceStore


class EnvironmentServiceError(RuntimeError):
    """Base class for stable environment application-service failures."""


class EnvironmentServiceNotFound(EnvironmentServiceError, KeyError):
    """Raised when required workspace/project/environment state is missing."""


class EnvironmentServiceConflict(EnvironmentServiceError):
    """Raised when a mutation conflicts with current durable state."""


class _EnvironmentContext:
    """Shared provider-neutral preflight over workspace/project metadata."""

    def __init__(
        self, workspace_store: WorkspaceStore, environment_store: EnvironmentStore
    ) -> None:
        self._workspace_store = workspace_store
        self._environment_store = environment_store

    def workspace(self, workspace_id: WorkspaceId, *, mutable: bool) -> Workspace:
        workspace = self._workspace_store.get_workspace(workspace_id)
        if workspace is None:
            raise EnvironmentServiceNotFound(f"workspace not found: {workspace_id}")
        if mutable and workspace.archived:
            raise EnvironmentServiceConflict("cannot mutate environments in an archived workspace")
        return workspace

    def project(self, workspace_id: WorkspaceId, project_id: ProjectId, *, mutable: bool) -> None:
        self.workspace(workspace_id, mutable=mutable)
        if self._workspace_store.get_project(workspace_id, project_id) is None:
            raise EnvironmentServiceNotFound(f"project not found: {workspace_id}/{project_id}")

    def environment(
        self,
        workspace_id: WorkspaceId,
        environment_id: EnvironmentId,
        *,
        mutable: bool,
    ) -> EnvironmentDefinition:
        self.workspace(workspace_id, mutable=mutable)
        environment = self._environment_store.get_environment(workspace_id, environment_id)
        if environment is None:
            raise EnvironmentServiceNotFound(
                f"environment not found: {workspace_id}/{environment_id}"
            )
        return environment


class EnvironmentService:
    """Application boundary for workspace-local environment definitions."""

    def __init__(
        self, workspace_store: WorkspaceStore, environment_store: EnvironmentStore
    ) -> None:
        self._environments = environment_store
        self._context = _EnvironmentContext(workspace_store, environment_store)

    def create(
        self,
        workspace_id: WorkspaceId,
        environment: EnvironmentDefinition,
        *,
        now: Instant | str,
    ) -> EnvironmentDefinition:
        self._context.workspace(workspace_id, mutable=True)
        existing = self._environments.get_environment(workspace_id, environment.id)
        if existing is not None:
            if existing == environment:
                return existing
            raise EnvironmentServiceConflict(
                f"environment id already exists with different intent: {environment.id}"
            )
        return self._environments.put_environment(workspace_id, environment, now=now)

    def get(
        self,
        workspace_id: WorkspaceId,
        environment_id: EnvironmentId,
    ) -> EnvironmentDefinition:
        return self._context.environment(workspace_id, environment_id, mutable=False)

    def list(self, workspace_id: WorkspaceId) -> tuple[EnvironmentDefinition, ...]:
        self._context.workspace(workspace_id, mutable=False)
        return self._environments.list_environments(workspace_id)

    def replace(
        self,
        workspace_id: WorkspaceId,
        environment: EnvironmentDefinition,
        *,
        now: Instant | str,
    ) -> EnvironmentDefinition:
        current = self._context.environment(workspace_id, environment.id, mutable=True)
        if current == environment:
            return current
        return self._environments.put_environment(workspace_id, environment, now=now)

    def disable(
        self,
        workspace_id: WorkspaceId,
        environment_id: EnvironmentId,
        *,
        now: Instant | str,
    ) -> EnvironmentDefinition:
        current = self._context.environment(workspace_id, environment_id, mutable=True)
        if current.disabled:
            return current
        disabled = replace(current, state="disabled")
        return self._environments.put_environment(workspace_id, disabled, now=now)


class DeploymentBindingService:
    """Application boundary for project/environment deployment bindings."""

    def __init__(
        self, workspace_store: WorkspaceStore, environment_store: EnvironmentStore
    ) -> None:
        self._environments = environment_store
        self._context = _EnvironmentContext(workspace_store, environment_store)

    def put(
        self,
        workspace_id: WorkspaceId,
        bindings: ProjectEnvironmentBindings,
        *,
        now: Instant | str,
    ) -> ProjectEnvironmentBindings:
        self._context.project(workspace_id, bindings.project_id, mutable=True)
        environment = self._context.environment(
            workspace_id,
            bindings.environment_id,
            mutable=True,
        )
        if environment.disabled:
            raise EnvironmentServiceConflict("cannot bind a project to a disabled environment")
        existing = self._environments.get_project_bindings(
            workspace_id,
            bindings.project_id,
            bindings.environment_id,
        )
        if existing == bindings:
            return existing
        return self._environments.put_project_bindings(workspace_id, bindings, now=now)

    def get(
        self,
        workspace_id: WorkspaceId,
        project_id: ProjectId,
        environment_id: EnvironmentId,
    ) -> ProjectEnvironmentBindings:
        self._context.project(workspace_id, project_id, mutable=False)
        self._context.environment(workspace_id, environment_id, mutable=False)
        bindings = self._environments.get_project_bindings(
            workspace_id,
            project_id,
            environment_id,
        )
        if bindings is None:
            raise EnvironmentServiceNotFound(
                "project environment bindings not found: "
                f"{workspace_id}/{project_id}/{environment_id}"
            )
        return bindings


__all__ = (
    "DeploymentBindingService",
    "EnvironmentService",
    "EnvironmentServiceConflict",
    "EnvironmentServiceError",
    "EnvironmentServiceNotFound",
)
