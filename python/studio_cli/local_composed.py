"""Composition root for the opt-in local composed HTTP profile."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

from studio_connectors import (
    IngestionHTTPAdapter,
    SqliteConnectorCheckpointStore,
    builtin_connector_registry,
)
from studio_core import (
    AssetHandle,
    ConnectionDefinition,
    ConnectionId,
    GrantSet,
    Workspace,
    WorkspaceId,
)
from studio_data_engineering import (
    PostgresQueryEvidenceReferenceStore,
    PostgresRevisionStore,
    RevisionApplication,
    SqliteQueryEvidenceReferenceStore,
    SqliteRevisionStore,
)
from studio_execution import (
    ConnectionService,
    DeploymentBindingService,
    DurableExecutionService,
    EnvironmentService,
    OntologyHTTPAdapter,
    PostgresWorkflowHTTPAdapter,
    ProjectService,
    SqliteWorkflowHTTPAdapter,
    WorkflowCancellationHTTPAdapter,
    WorkspaceService,
)
from studio_finops import SqliteFinOpsStore
from studio_ml import PostgresMLLabStore
from studio_ml.sqlite import SqliteMLLabStore
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
    CompositeSecretResolver,
    EnvironmentSecretResolver,
    LocalArtifactStore,
    PostgresArtifactReferenceBarrier,
    PostgresAuditStore,
    PostgresJobReadPort,
    PostgresMLStore,
    PostgresSchedulerSnapshotStore,
    SqliteAuditStore,
    SqliteCatalogStore,
    SqliteConnectionStore,
    SqliteEnvironmentStore,
    SqliteJobStore,
    SqliteKnowledgeGraphStore,
    SqliteOntologyStore,
    SqliteQualityStore,
)
from studio_storage.bundle_workflow_import import SqliteWorkflowBundleImportStore
from studio_storage.ml import SqliteMLStore
from studio_synthetic_data import GovernStudioService, SqliteRunStore


class _LocalDataEngineeringRevisions:
    def __init__(
        self,
        records: Any,
        artifact_root: Path,
        artifact_reference_barrier: Any = None,
    ) -> None:
        self._records = records
        self._application = RevisionApplication(
            LocalArtifactStore(artifact_root),
            self._records,
            artifact_reference_barrier=artifact_reference_barrier,
        )

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


def _workflow_reader_for_backend(
    scheduler: Any, *, now: Instant, postgres_dsn: str | None
) -> Any | None:
    """Expose workflow routes only when the selected store supports every route operation."""
    if postgres_dsn is not None:
        required = (
            "list_workflows",
            "put_workflow",
            "list_schedules",
            "get_schedule",
            "put_schedule",
            "list_schedule_fires",
            "get_event",
            "list_event_triggers",
            "put_event_trigger",
            "ingest_event",
            "list_pending_deliveries",
            "create_backfill",
            "get_backfill",
            "cancel_backfill",
            "get_run",
            "list_task_runs",
            "create_run",
        )
        if not all(callable(getattr(scheduler, name, None)) for name in required):
            return None
        return PostgresWorkflowHTTPAdapter(cast(Any, scheduler), now=now)
    return SqliteWorkflowHTTPAdapter(cast(Any, scheduler), now=now)


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
        "scheduler.read,scheduler.write,workspace.read,workspace.write,project.read",
    )
    permissions = frozenset(
        cast(Permission, item.strip()) for item in raw_permissions.split(",") if item.strip()
    )
    if not permissions or not permissions <= {
        "scheduler.read",
        "scheduler.write",
        "workspace.read",
        "workspace.write",
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
    artifact_store = LocalArtifactStore(database.parent / "artifacts")
    artifact_reference_barrier = (
        PostgresArtifactReferenceBarrier(
            postgres_dsn,
            application_name="ronin-composed-artifact-retention",
        )
        if postgres_dsn is not None
        else None
    )
    job_server = RoninHTTPServer(
        (_env("RONIN_HOST", "127.0.0.1"), _port("RONIN_PORT", "8080")),
        job_service,
        token=_env("RONIN_TOKEN"),
        grants=job_grants,
    )
    scheduler = (
        PostgresSchedulerSnapshotStore(
            postgres_dsn,
            application_name="ronin-composed-workflows",
        )
        if postgres_dsn is not None
        else SqliteWorkflowBundleImportStore(database, migration_now=now)
    )
    catalog_store = (
        SqliteCatalogStore(database, migration_now=now) if postgres_dsn is None else scheduler
    )
    workspace_service = WorkspaceService(scheduler)
    project_service = ProjectService(scheduler)
    try:
        workspace_service.get(workspace_id)
    except KeyError:
        workspace_service.create(
            Workspace(workspace_id, "Local workspace", "Workspace managed by the local profile"),
            now=now,
        )
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
            "ml_execution_service": job_service,
            "ml_registry": (
                PostgresMLStore(postgres_dsn, application_name="ronin-composed-ml-registry")
                if postgres_dsn is not None
                else SqliteMLStore(database, migration_now=now)
            ),
            "artifact_store": artifact_store,
            "artifact_reference_barrier": artifact_reference_barrier,
            "queryflux_evidence_reference_store": (
                PostgresQueryEvidenceReferenceStore(postgres_dsn)
                if postgres_dsn is not None
                else SqliteQueryEvidenceReferenceStore(database)
            ),
            "govern_studio_service": GovernStudioService(
                SqliteRunStore(str(database.parent / "synthetic-data.sqlite3"))
            ),
            "catalog_store": catalog_store,
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
    catalog_reader = cast(Any, catalog_store) if postgres_dsn is None else None
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
    connection_store = (
        SqliteConnectionStore(database, migration_now=now) if postgres_dsn is None else scheduler
    )
    connection_service = ConnectionService(scheduler, cast(Any, connection_store))
    connector_registry = builtin_connector_registry()
    ingestion_adapter = None
    if postgres_dsn is None:
        checkpoint_store = SqliteConnectorCheckpointStore(database)
        secrets_resolver = CompositeSecretResolver(environment=EnvironmentSecretResolver())

        def resolve_connection(scoped_workspace_id: str, reference: str) -> ConnectionDefinition:
            return connection_service.get(WorkspaceId(scoped_workspace_id), ConnectionId(reference))

        def resolve_asset(reference: str) -> AssetHandle:
            if "::" not in reference:
                raise ValueError(
                    "asset_ref must use connection_id::qualified_asset_name in the local profile"
                )
            connection_ref, qualified_name = reference.split("::", 1)
            parts = tuple(qualified_name.split("."))
            if not connection_ref or not parts or any(not part for part in parts):
                raise ValueError("asset_ref must contain a connection id and qualified asset name")
            return AssetHandle(ConnectionId(connection_ref), parts[:-1], parts[-1])

        ingestion_adapter = IngestionHTTPAdapter(
            connector_registry,
            checkpoint_store,
            resolve_connection,
            resolve_asset,
            lambda _reference: secrets_resolver,
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
            PostgresRevisionStore(postgres_dsn),
            database.parent / "artifacts",
            artifact_reference_barrier,
        )
    )
    control_server = WorkspaceProjectHTTPServer(
        (_env("RONIN_HOST", "127.0.0.1"), _port("RONIN_CONTROL_PLANE_PORT", "8081")),
        workspace_service,
        project_service,
        authenticator=StaticControlPlaneAuthenticator(control_token),
        authorizer=StaticControlPlaneAuthorizer(workspace_id, permissions),
        workflow_reader=_workflow_reader_for_backend(scheduler, now=now, postgres_dsn=postgres_dsn),
        workflow_canceller=(
            WorkflowCancellationHTTPAdapter(scheduler, job_service)
            if postgres_dsn is not None
            else None
        ),
        graph_query_reader=cast(Any, graph_adapter),
        ontology_reader=graph_adapter,
        catalog_reader=catalog_reader,
        semantic_reader=semantic_reader,
        environment_service=environment_service,
        connection_service=connection_service,
        binding_service=binding_service,
        quality_reader=quality_reader,
        finops_reader=finops_reader,
        data_engineering_reader=data_engineering_reader,
        connector_registry=connector_registry,
        ingestion_adapter=ingestion_adapter,
        plugin_host=plugin_host,
        plugin_routes_enabled=plugin_routes_enabled,
    )
    return LocalServerComposition(job_server, control_server, plugin_host=plugin_host)


__all__ = ("build_local_composed_from_env",)
