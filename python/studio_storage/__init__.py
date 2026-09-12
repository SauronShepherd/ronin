"""Transactional persistence behind the pure job-store contract."""

from __future__ import annotations

from studio_storage.artifacts import ArtifactIntegrityError, ArtifactRef, LocalArtifactStore
from studio_storage.async_artifacts import BoundedAsyncArtifactStore
from studio_storage.async_store import StorageBackpressureError
from studio_storage.bundle import (
    BUNDLE_MANIFEST_PATH,
    BundleFile,
    BundleIntegrityError,
    BundleReadLimits,
    extract_bundle,
    verify_bundle,
    write_bundle,
)
from studio_storage.catalog import (
    CatalogAssetNotFound,
    CatalogConflict,
    SqliteCatalogStore,
    catalog_schema_version,
    migrate_catalog,
)
from studio_storage.connections import (
    ConnectionConflict,
    ConnectionNotFound,
    SqliteConnectionStore,
    connection_schema_version,
    migrate_connections,
)
from studio_storage.fenced_sqlite import SqliteJobStore
from studio_storage.memory import IdempotencyConflict
from studio_storage.ontology import (
    OntologyConflict,
    SqliteOntologyStore,
    migrate_ontology,
    ontology_schema_version,
)
from studio_storage.paged_store import BoundedAsyncJobStore, InMemoryJobStore
from studio_storage.quality import (
    DataContractConflict,
    DataContractNotFound,
    QualityRunConflict,
    SqliteQualityStore,
    migrate_quality,
    quality_schema_version,
)
from studio_storage.readiness import sqlite_ready
from studio_storage.scheduler import (
    SqliteSchedulerStore,
    WorkflowConflict,
    WorkflowNotFound,
    WorkflowRunConflict,
    migrate_scheduler,
    scheduler_schema_version,
)
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
    "BUNDLE_MANIFEST_PATH",
    "BoundedAsyncArtifactStore",
    "BoundedAsyncJobStore",
    "BundleFile",
    "BundleIntegrityError",
    "BundleReadLimits",
    "CatalogAssetNotFound",
    "CatalogConflict",
    "ConnectionConflict",
    "ConnectionNotFound",
    "DataContractConflict",
    "DataContractNotFound",
    "IdempotencyConflict",
    "InMemoryJobStore",
    "LocalArtifactStore",
    "OntologyConflict",
    "ProjectRegistrationConflict",
    "QualityRunConflict",
    "SqliteCatalogStore",
    "SqliteConnectionStore",
    "SqliteJobStore",
    "SqliteOntologyStore",
    "SqliteQualityStore",
    "SqliteSchedulerStore",
    "SqliteWorkspaceStore",
    "StorageBackpressureError",
    "WorkflowConflict",
    "WorkflowNotFound",
    "WorkflowRunConflict",
    "WorkspaceConflict",
    "WorkspaceNotFound",
    "catalog_schema_version",
    "connection_schema_version",
    "extract_bundle",
    "migrate",
    "migrate_catalog",
    "migrate_connections",
    "migrate_ontology",
    "migrate_quality",
    "migrate_scheduler",
    "migrate_workspaces",
    "ontology_schema_version",
    "open_database",
    "quality_schema_version",
    "scheduler_schema_version",
    "schema_version",
    "sqlite_ready",
    "verify_bundle",
    "workspace_schema_version",
    "write_bundle",
)