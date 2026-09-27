"""Composition root for the opt-in local composed HTTP profile."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

from studio_core import GrantSet, WorkspaceId
from studio_data_engineering import (
    PostgresRevisionStore,
    RevisionApplication,
    SqliteRevisionStore,
)
from studio_execution import (
    DeploymentBindingService,
    DurableExecutionService,
    EnvironmentService,
    OntologyHTTPAdapter,
    ProjectService,
    SqliteWorkflowHTTPAdapter,
    WorkspaceService,
)
from studio_finops import SqliteFinOpsStore
from studio_ml import PostgresExecutionStore, PostgresMLLabStore
from studio_ml.sqlite import SqliteExecutionStore, SqliteMLLabStore
from studio_orchestrator import Instant
from studio_plugin_observability import LocalObservabilityBuffer
from studio_runtime import PluginAuditSink, PluginHost, PluginLock, PluginLockError
from studio_security import Permission
from studio_semantic import ProjectScopedSemanticRuntime, SemanticHTTPAdapter, SqliteSemanticStore
from studio_server import (
    LocalServerComposition,
    QualityHTTPAdapter,
    RoninHTTPServer,
    StaticControlPlaneAuthenticator,
    StaticControlPlaneAuthorizer,
    WorkspaceProjectHTTPServer,
)
from studio_sql import ProjectScopedDuckDbSqlEngine
from studio_storage import (
    LocalArtifactStore,
    PostgresAuditStore,
    PostgresJobReadPort,
    PostgresMLStore,
    PostgresWorkflowBundleImportStore,
    SqliteAuditStore,
    SqliteCatalogStore,
    SqliteEnvironmentStore,
    SqliteJobStore,
    SqliteKnowledgeGraphStore,
    SqliteOntologyStore,
    SqliteQualityStore,
)
from studio_storage.bundle_workflow_import import SqliteWorkflowBundleImportStore
from studio_storage.ml import SqliteMLStore


class _LocalDataEngineeringRevisions:
    def __init__(self, records: Any, artifact_root: Path) -> None:
        self._records = records
        self._application = RevisionApplication(LocalArtifactStore(artifact_root), self._records)

    def list_revisions(self, *, project_id: str, pipeline_id: str) -> Any:
        return self._records.list_revisions(project_id=project_id, pipeline_id=pipeline_id)

    def list_pipelines(self, *, project_id: str) -> Any:
        return self._records.list_pipelines(project_id=project_id)

    def get_revision(self, *, project_id: str, pipeline_id: str, revision: int) -> Any:
        return self._records.get_revision(
            project_id=project_id, pipeline_id=pipeline_id, revision=revision
        )

    def compare(
        self, *, project_id: str, pipeline_id: str, left_revision: int, right_revision: int
    ) -> Any:
        return self._records.compare(
            project_id=project_id,
            pipeline_id=pipeline_id,
            left_revision=left_revision,
            right_revision=right_revision,
        )

    def archive(self, *, project_id: str, pipeline_id: str) -> bool:
        return bool(self._records.archive(project_id=project_id, pipeline_id=pipeline_id))

    def import_sdp(
        self,
        *,
        project_id: str,
        pipeline_id: str,
        source: Any,
        expected_revision: int | None = None,
    ) -> Any:
        return self._application.import_sdp(
            project_id=project_id,
            pipeline_id=pipeline_id,
            source=source,
            expected_revision=expected_revision,
        )


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty and trimmed")
    return value


def _port(name: str, default: str) -> int:
    try:
        value = int(_env(name, default))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not 1 <= value <= 65535:
        raise ValueError(f"{name} must be between 1 and 65535")
    return value


def build_local_composed_from_env() -> LocalServerComposition:
    """Build, but do not start, the opt-in two-surface local profile."""

    database = Path(_env("RONIN_DB", ".ronin/ronin.sqlite3")).expanduser().resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    storage_backend = _env("RONIN_STORAGE_BACKEND", "sqlite").casefold()
    if storage_backend not in {"sqlite", "postgres"}:
        raise ValueError("RONIN_STORAGE_BACKEND must be sqlite or postgres")
    postgres_dsn = _env("RONIN_POSTGRES_DSN") if storage_backend == "postgres" else None
    now = Instant("2026-09-17T00:00:00.000000Z")
    workspace_id = WorkspaceId(_env("RONIN_WORKSPACE_ID"))
    control_token = _env("RONIN_CONTROL_PLANE_TOKEN")
    raw_permissions = _env(
        "RONIN_CONTROL_PLANE_PERMISSIONS",
        "scheduler.read,scheduler.write,workspace.read,project.read",
    )
    permissions = frozenset(
        cast(Permission, item.strip()) for item in raw_permissions.split(",") if item.strip()
    )
    if not permissions or not permissions <= {
        "scheduler.read",
        "scheduler.write",
        "workspace.read",
        "workspace.admin",
        "project.read",
        "project.write",
    }:
        raise ValueError("RONIN_CONTROL_PLANE_PERMISSIONS contains unsupported permissions")

    job_store = (
        PostgresJobReadPort(postgres_dsn, application_name="ronin-composed-jobs")
        if postgres_dsn is not None
        else SqliteJobStore(database, migration_now=now)
    )
    job_service = DurableExecutionService(job_store)
    try:
        job_grants = GrantSet.from_json(_env("RONIN_TOKEN_SCOPES"))
    except ValueError as exc:
        raise ValueError(f"invalid RONIN_TOKEN_SCOPES: {exc}") from exc
    job_server = RoninHTTPServer(
        (_env("RONIN_HOST", "127.0.0.1"), _port("RONIN_PORT", "8080")),
        job_service,
        token=_env("RONIN_TOKEN"),
        grants=job_grants,
    )
    scheduler = (
        PostgresWorkflowBundleImportStore(
            postgres_dsn,
            application_name="ronin-composed-workflows",
        )
        if postgres_dsn is not None
        else SqliteWorkflowBundleImportStore(database, migration_now=now)
    )
    workspace_service = WorkspaceService(scheduler)
    project_service = ProjectService(scheduler)
    audit_store = (
        PostgresAuditStore(postgres_dsn, application_name="ronin-composed-audit")
        if postgres_dsn is not None
        else SqliteAuditStore(database, migration_now=now)
    )
    observability_buffer = LocalObservabilityBuffer()
    plugin_host = PluginHost.discover(
        services={
            "workspace_service": workspace_service,
            "project_service": project_service,
            "observability_buffer": observability_buffer,
            "ml_lab_store": (
                PostgresMLLabStore(postgres_dsn, application_name="ronin-composed-ml")
                if postgres_dsn is not None
                else SqliteMLLabStore(database, migration_now=now)
            ),
            "ml_execution_store": (
                PostgresExecutionStore(postgres_dsn, application_name="ronin-composed-ml-execution")
                if postgres_dsn is not None
                else SqliteExecutionStore(database)
            ),
            "ml_registry": (
                PostgresMLStore(postgres_dsn, application_name="ronin-composed-ml-registry")
                if postgres_dsn is not None
                else SqliteMLStore(database, migration_now=now)
            ),
            "artifact_store": LocalArtifactStore(database.parent / "artifacts"),
        }
    )
    plugin_host.audit = PluginAuditSink(audit_store.append, workspace_id)
    lock_path = os.environ.get("RONIN_PLUGIN_LOCK")
    if lock_path is not None:
        try:
            lock = PluginLock.read(str(Path(lock_path).expanduser().resolve()))
            plugin_host.verify_lock(lock)
        except (OSError, PluginLockError) as exc:
            raise ValueError(f"RONIN_PLUGIN_LOCK validation failed: {exc}") from exc
    plugin_api_mode = os.environ.get("RONIN_PLUGIN_API", "plugin")
    if plugin_api_mode not in {"legacy", "plugin"}:
        raise ValueError("RONIN_PLUGIN_API must be legacy or plugin")
    plugin_routes_enabled = plugin_api_mode == "plugin"
    graph_adapter = (
        OntologyHTTPAdapter(
            cast(Any, SqliteOntologyStore(database, migration_now=now)),
            SqliteKnowledgeGraphStore(database),
        )
        if postgres_dsn is None
        else None
    )
    catalog_reader = (
        SqliteCatalogStore(database, migration_now=now) if postgres_dsn is None else None
    )
    semantic_reader = None
    try:
        semantic_reader = SemanticHTTPAdapter(
            SqliteSemanticStore(database),
            ProjectScopedSemanticRuntime(ProjectScopedDuckDbSqlEngine()),
        )
    except Exception as exc:
        if postgres_dsn is None and os.environ.get("RONIN_SEMANTIC_REQUIRED") == "1":
            raise ValueError(f"semantic runtime is required but unavailable: {exc}") from exc
    environment_store = (
        SqliteEnvironmentStore(database, migration_now=now) if postgres_dsn is None else None
    )
    environment_service = (
        EnvironmentService(scheduler, environment_store) if environment_store is not None else None
    )
    binding_service = (
        DeploymentBindingService(scheduler, environment_store)
        if environment_store is not None
        else None
    )
    quality_reader = (
        QualityHTTPAdapter(SqliteQualityStore(database, migration_now=now))
        if postgres_dsn is None
        else None
    )
    finops_reader = SqliteFinOpsStore(database) if postgres_dsn is None else None
    data_engineering_reader = (
        _LocalDataEngineeringRevisions(SqliteRevisionStore(database), database.parent / "artifacts")
        if postgres_dsn is None
        else _LocalDataEngineeringRevisions(
            PostgresRevisionStore(postgres_dsn), database.parent / "artifacts"
        )
    )
    control_server = WorkspaceProjectHTTPServer(
        (_env("RONIN_HOST", "127.0.0.1"), _port("RONIN_CONTROL_PLANE_PORT", "8081")),
        workspace_service,
        project_service,
        authenticator=StaticControlPlaneAuthenticator(control_token),
        authorizer=StaticControlPlaneAuthorizer(workspace_id, permissions),
        workflow_reader=cast(Any, SqliteWorkflowHTTPAdapter(cast(Any, scheduler), now=now)),
        graph_query_reader=cast(Any, graph_adapter),
        ontology_reader=graph_adapter,
        catalog_reader=catalog_reader,
        semantic_reader=semantic_reader,
        environment_service=environment_service,
        binding_service=binding_service,
        quality_reader=quality_reader,
        finops_reader=finops_reader,
        data_engineering_reader=data_engineering_reader,
        plugin_host=plugin_host,
        plugin_routes_enabled=plugin_routes_enabled,
    )
    return LocalServerComposition(job_server, control_server, plugin_host=plugin_host)


__all__ = ("build_local_composed_from_env",)
