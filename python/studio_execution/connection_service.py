"""Provider-neutral application service for workspace-scoped connections."""

from __future__ import annotations

from studio_core import ConnectionDefinition, ConnectionId, WorkspaceId
from studio_orchestrator import Instant
from studio_storage.ports import ConnectionStore, WorkspaceStore


class ConnectionServiceError(RuntimeError):
    """Base class for stable connection application-service failures."""


class ConnectionServiceNotFound(ConnectionServiceError, KeyError):
    """Raised when a required workspace or connection does not exist."""


class ConnectionServiceConflict(ConnectionServiceError):
    """Raised when a connection mutation conflicts with durable intent."""


class ConnectionService:
    """Application boundary for portable, secret-reference-only connection definitions."""

    def __init__(self, workspace_store: WorkspaceStore, connection_store: ConnectionStore) -> None:
        self._workspaces = workspace_store
        self._connections = connection_store

    def _workspace(self, workspace_id: WorkspaceId, *, mutable: bool) -> None:
        workspace = self._workspaces.get_workspace(workspace_id)
        if workspace is None:
            raise ConnectionServiceNotFound(f"workspace not found: {workspace_id}")
        if mutable and workspace.archived:
            raise ConnectionServiceConflict("cannot mutate connections in an archived workspace")

    def create(
        self,
        workspace_id: WorkspaceId,
        definition: ConnectionDefinition,
        *,
        now: Instant | str,
    ) -> ConnectionDefinition:
        self._workspace(workspace_id, mutable=True)
        existing = self._connections.get_connection(workspace_id, definition.id)
        if existing is not None:
            if existing == definition:
                return existing
            raise ConnectionServiceConflict(
                f"connection id already exists with different intent: {definition.id}"
            )
        return self._connections.create_connection(workspace_id, definition, now=now)

    def get(
        self,
        workspace_id: WorkspaceId,
        connection_id: ConnectionId,
    ) -> ConnectionDefinition:
        self._workspace(workspace_id, mutable=False)
        definition = self._connections.get_connection(workspace_id, connection_id)
        if definition is None:
            raise ConnectionServiceNotFound(
                f"connection not found: {workspace_id}/{connection_id}"
            )
        return definition

    def list(self, workspace_id: WorkspaceId) -> tuple[ConnectionDefinition, ...]:
        self._workspace(workspace_id, mutable=False)
        return self._connections.list_connections(workspace_id)

    def replace(
        self,
        workspace_id: WorkspaceId,
        definition: ConnectionDefinition,
        *,
        now: Instant | str,
    ) -> ConnectionDefinition:
        self._workspace(workspace_id, mutable=True)
        existing = self._connections.get_connection(workspace_id, definition.id)
        if existing is None:
            raise ConnectionServiceNotFound(
                f"connection not found: {workspace_id}/{definition.id}"
            )
        if existing == definition:
            return existing
        return self._connections.replace_connection(workspace_id, definition, now=now)

    def delete(self, workspace_id: WorkspaceId, connection_id: ConnectionId) -> None:
        self._workspace(workspace_id, mutable=True)
        if self._connections.get_connection(workspace_id, connection_id) is None:
            raise ConnectionServiceNotFound(
                f"connection not found: {workspace_id}/{connection_id}"
            )
        if not self._connections.delete_connection(workspace_id, connection_id):
            raise ConnectionServiceNotFound(
                f"connection not found: {workspace_id}/{connection_id}"
            )


__all__ = (
    "ConnectionService",
    "ConnectionServiceConflict",
    "ConnectionServiceError",
    "ConnectionServiceNotFound",
)
