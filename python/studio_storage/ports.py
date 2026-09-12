"""Provider-neutral persistence ports for Public v1 control-plane services.

These protocols deliberately model existing Ronin semantics instead of exposing
SQL/ORM primitives. SQLite remains the reference adapter; PostgreSQL adapters
can implement the same contracts without changing service/domain behavior.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from studio_core import (
    AssetId,
    AssetRef,
    AssetRevision,
    CatalogAsset,
    ConnectionDefinition,
    ConnectionId,
    LineageEdge,
    ProjectId,
    ProjectManifest,
    Workspace,
    WorkspaceId,
)
from studio_core.environments import (
    EnvironmentDefinition,
    EnvironmentId,
    ProjectEnvironmentBindings,
)
from studio_orchestrator import Instant
from studio_storage.artifacts import ArtifactRef


@runtime_checkable
class ArtifactStore(Protocol):
    """Content-addressed artifact storage independent of physical backend."""

    def put_bytes(
        self,
        *,
        role: str,
        data: bytes,
        media_type: str | None = None,
    ) -> ArtifactRef: ...

    def get_bytes(self, ref: ArtifactRef) -> bytes: ...

    def verify(self, ref: ArtifactRef) -> bool: ...


@runtime_checkable
class WorkspaceStore(Protocol):
    """Durable workspace/project-registration boundary."""

    def create_workspace(self, workspace: Workspace, *, now: Instant | str) -> Workspace: ...

    def get_workspace(self, workspace_id: WorkspaceId) -> Workspace | None: ...

    def list_workspaces(self) -> tuple[Workspace, ...]: ...

    def update_workspace(self, workspace: Workspace, *, now: Instant | str) -> Workspace: ...

    def register_project(
        self,
        workspace_id: WorkspaceId,
        manifest: ProjectManifest,
        *,
        now: Instant | str,
    ) -> ProjectManifest: ...

    def replace_project(
        self,
        workspace_id: WorkspaceId,
        manifest: ProjectManifest,
        *,
        now: Instant | str,
    ) -> ProjectManifest: ...

    def get_project(
        self,
        workspace_id: WorkspaceId,
        project_id: ProjectId,
    ) -> ProjectManifest | None: ...

    def list_projects(self, workspace_id: WorkspaceId) -> tuple[ProjectManifest, ...]: ...

    def unregister_project(self, workspace_id: WorkspaceId, project_id: ProjectId) -> bool: ...


@runtime_checkable
class EnvironmentStore(Protocol):
    """Durable environment and project-binding boundary."""

    def put_environment(
        self,
        workspace_id: WorkspaceId,
        environment: EnvironmentDefinition,
        *,
        now: Instant | str,
    ) -> EnvironmentDefinition: ...

    def get_environment(
        self,
        workspace_id: WorkspaceId,
        environment_id: EnvironmentId,
    ) -> EnvironmentDefinition | None: ...

    def list_environments(self, workspace_id: WorkspaceId) -> tuple[EnvironmentDefinition, ...]: ...

    def put_project_bindings(
        self,
        workspace_id: WorkspaceId,
        bindings: ProjectEnvironmentBindings,
        *,
        now: Instant | str,
    ) -> ProjectEnvironmentBindings: ...

    def get_project_bindings(
        self,
        workspace_id: WorkspaceId,
        project_id: ProjectId,
        environment_id: EnvironmentId,
    ) -> ProjectEnvironmentBindings | None: ...


@runtime_checkable
class ConnectionStore(Protocol):
    """Durable connection-definition boundary; credentials remain SecretRefs."""

    def create_connection(
        self,
        workspace_id: WorkspaceId,
        definition: ConnectionDefinition,
        *,
        now: Instant | str,
    ) -> ConnectionDefinition: ...

    def replace_connection(
        self,
        workspace_id: WorkspaceId,
        definition: ConnectionDefinition,
        *,
        now: Instant | str,
    ) -> ConnectionDefinition: ...

    def get_connection(
        self,
        workspace_id: WorkspaceId,
        connection_id: ConnectionId,
    ) -> ConnectionDefinition | None: ...

    def list_connections(self, workspace_id: WorkspaceId) -> tuple[ConnectionDefinition, ...]: ...

    def delete_connection(self, workspace_id: WorkspaceId, connection_id: ConnectionId) -> bool: ...


@runtime_checkable
class CatalogStore(Protocol):
    """Durable governed-asset/revision/lineage boundary."""

    def create_asset(
        self,
        workspace_id: WorkspaceId,
        asset: CatalogAsset,
        *,
        now: Instant | str,
    ) -> CatalogAsset: ...

    def replace_asset(
        self,
        workspace_id: WorkspaceId,
        asset: CatalogAsset,
        *,
        now: Instant | str,
    ) -> CatalogAsset: ...

    def get_asset(self, workspace_id: WorkspaceId, asset_id: AssetId) -> CatalogAsset | None: ...

    def list_assets(self, workspace_id: WorkspaceId) -> tuple[CatalogAsset, ...]: ...

    def put_revision(
        self,
        workspace_id: WorkspaceId,
        revision: AssetRevision,
        *,
        now: Instant | str,
    ) -> AssetRevision: ...

    def get_revision(self, workspace_id: WorkspaceId, ref: AssetRef) -> AssetRevision | None: ...

    def put_lineage(
        self,
        workspace_id: WorkspaceId,
        edge: LineageEdge,
        *,
        now: Instant | str,
    ) -> LineageEdge: ...

    def upstream(self, workspace_id: WorkspaceId, ref: AssetRef) -> tuple[LineageEdge, ...]: ...

    def downstream(self, workspace_id: WorkspaceId, ref: AssetRef) -> tuple[LineageEdge, ...]: ...


__all__ = (
    "ArtifactStore",
    "CatalogStore",
    "ConnectionStore",
    "EnvironmentStore",
    "WorkspaceStore",
)
