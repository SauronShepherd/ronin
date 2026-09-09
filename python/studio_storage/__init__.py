"""Transactional persistence behind the pure job-store contract."""

from __future__ import annotations

from studio_storage.artifacts import ArtifactIntegrityError, ArtifactRef, LocalArtifactStore
from studio_storage.async_artifacts import BoundedAsyncArtifactStore
from studio_storage.async_store import StorageBackpressureError
from studio_storage.fenced_sqlite import SqliteJobStore
from studio_storage.memory import IdempotencyConflict
from studio_storage.paged_store import BoundedAsyncJobStore, InMemoryJobStore
from studio_storage.sqlite import migrate, open_database, schema_version

__all__ = (
    "ArtifactIntegrityError",
    "ArtifactRef",
    "BoundedAsyncArtifactStore",
    "BoundedAsyncJobStore",
    "IdempotencyConflict",
    "InMemoryJobStore",
    "LocalArtifactStore",
    "SqliteJobStore",
    "StorageBackpressureError",
    "migrate",
    "open_database",
    "schema_version",
)
