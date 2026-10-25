"""Workspace-scoped connector sync composition for local worker runtimes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from studio_connectors import (
    ArtifactDestinationWriter,
    IngestionSyncService,
    PostgresConnectorCheckpointStore,
    SqliteConnectorCheckpointStore,
    builtin_connector_registry,
)
from studio_core import (
    AssetHandle,
    ConnectionDefinition,
    ConnectionId,
    WorkspaceId,
)
from studio_orchestrator import Instant
from studio_storage import (
    ArtifactStore,
    CompositeSecretResolver,
    EnvironmentSecretResolver,
    PostgresMetadataStore,
    SqliteConnectionStore,
    SqliteWorkspaceStore,
)
from studio_storage.ports import ArtifactReferenceBarrier

from .connection_service import ConnectionService


@dataclass(frozen=True, slots=True)
class ConnectorSyncDependencies:
    """Resolved ports needed to dispatch a workspace-scoped connector sync."""

    service: IngestionSyncService
    connection: Callable[[str, str], ConnectionDefinition]
    asset: Callable[[ConnectionDefinition, str], AssetHandle]
    secrets: Callable[[str], CompositeSecretResolver]
    destination: ArtifactDestinationWriter


def build_connector_sync_dependencies(
    *,
    workspace_id: str,
    postgres_dsn: str | None,
    database_path: Path,
    artifact_store: ArtifactStore,
    artifact_reference_barrier: ArtifactReferenceBarrier | None,
    migration_now: Instant,
) -> ConnectorSyncDependencies:
    """Create connector sync ports, confined to the worker's configured workspace."""

    if not workspace_id or workspace_id != workspace_id.strip():
        raise ValueError("connector workspace_id must be non-empty and trimmed")
    if postgres_dsn is not None:
        metadata_store = PostgresMetadataStore(
            postgres_dsn, application_name="ronin-worker-connectors"
        )
        connection_service = ConnectionService(metadata_store, metadata_store)
        checkpoints: PostgresConnectorCheckpointStore | SqliteConnectorCheckpointStore = (
            PostgresConnectorCheckpointStore(postgres_dsn)
        )
    else:
        workspaces = SqliteWorkspaceStore(database_path, migration_now=migration_now)
        connections = SqliteConnectionStore(database_path, migration_now=migration_now)
        connection_service = ConnectionService(workspaces, connections)
        checkpoints = SqliteConnectorCheckpointStore(database_path)

    secrets = CompositeSecretResolver(environment=EnvironmentSecretResolver())
    service = IngestionSyncService(
        builtin_connector_registry(),
        checkpoints,
        artifact_reference_barrier=artifact_reference_barrier,
    )

    def resolve_connection(requested_workspace: str, reference: str) -> ConnectionDefinition:
        if requested_workspace != workspace_id:
            raise ValueError("connector sync workspace does not match the configured worker scope")
        return connection_service.get(WorkspaceId(workspace_id), ConnectionId(reference))

    def resolve_asset(connection: ConnectionDefinition, reference: str) -> AssetHandle:
        separator = (
            "/"
            if connection.connector_id
            in {
                "azure.blob.json",
                "http.json",
                "ozone.s3.json",
                "s3.json",
            }
            else "."
        )
        components = tuple(reference.split(separator))
        if not components or any(
            not component or component in {".", ".."} or "\\" in component
            for component in components
        ):
            raise ValueError("connector sync asset reference has invalid components")
        return AssetHandle(connection.id, components[:-1], components[-1])

    def resolve_secrets(_reference: str) -> CompositeSecretResolver:
        return secrets

    return ConnectorSyncDependencies(
        service=service,
        connection=resolve_connection,
        asset=resolve_asset,
        secrets=resolve_secrets,
        destination=ArtifactDestinationWriter(artifact_store),
    )


__all__ = ("ConnectorSyncDependencies", "build_connector_sync_dependencies")
