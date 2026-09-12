"""Transactional persistence behind the pure job-store contract."""

from __future__ import annotations

from studio_storage.artifacts import ArtifactIntegrityError, ArtifactRef, LocalArtifactStore
from studio_storage.async_artifacts import BoundedAsyncArtifactStore
from studio_storage.async_store import StorageBackpressureError
from studio_storage.connections import (
    ConnectionConflict,
    ConnectionNotFound,
    SqliteConnectionStore,
    connection_schema_version,
    migrate_connections,
)
from studio_storage.fenced_sqlite import SqliteJobStore
from studio_storage.memory import IdempotencyConflict
from studio_storage.paged_store import BoundedAsyncJobStore, InMemoryJobStore
from studio_storage.readiness import sqlite_ready
from studio_storage.sqlite import migrate, open_database, schema_version
from studio_storage.workspaces import (
    ProjectRegistrationConflict,
    SqliteWorkspaceStore,
    WorkspaceConflict,
    WorkspaceNotFound,
    migrate_workspaces,
    workspace_schema_version,
)

__all__ = (
    "ArtifactIntegrityError",
    "ArtifactRef",
    "BoundedAsyncArtifactStore",
    "BoundedAsyncJobStore",
    "ConnectionConflict",
    "ConnectionNotFound",
    "IdempotencyConflict",
    "InMemoryJobStore",
    "LocalArtifactStore",
    "ProjectRegistrationConflict",
    "SqliteConnectionStore",
    "SqliteJobStore",
    "SqliteWorkspaceStore",
    "StorageBackpressureError",
    "WorkspaceConflict",
    "WorkspaceNotFound",
    "connection_schema_version",
    "migrate",
    "migrate_connections",
    "migrate_workspaces",
    "open_database",
    "schema_version",
    "sqlite_ready",
    "workspace_schema_version",
)