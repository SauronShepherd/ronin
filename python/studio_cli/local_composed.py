"""Composition root for the opt-in local composed HTTP profile."""

from __future__ import annotations

import math
import os
import secrets
from contextlib import suppress
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Any, cast

from studio_connectors import (
    IngestionHTTPAdapter,
    PostgresConnectorCheckpointStore,
    SqliteConnectorCheckpointStore,
    builtin_connector_registry,
)
from studio_core import (
    AssetHandle,
    ConnectionDefinition,
    ConnectionId,
    GrantSet,
    QualityRun,
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
from studio_execution.scheduler_daemon import (
    BackfillTarget,
    SchedulerDaemon,
    SchedulerDaemonService,
    SchedulerDaemonWork,
)
from studio_finops import SqliteFinOpsStore
from studio_migration import (
    MigrationAPIRouter,
    MigrationSessionService,
    SQLiteMigrationSessionStore,
)
from studio_ml import FeatureDefinitionService, PostgresMLLabStore
from studio_ml.sqlite import SqliteMLLabStore
from studio_notebook import ProjectNotebookHTTPAdapter
from studio_observability import (
    AlertHTTPAdapter,
    SqliteTelemetryStore,
    evaluate_quality_alerts,
    record_quality_metrics,
)
from studio_orchestrator import Instant, LeaseToken
from studio_plugin_observability import LocalObservabilityBuffer
from studio_runtime import PluginAuditSink, PluginHost, PluginLock, PluginLockError
from studio_security import Actor, Permission, mutation_audit_event
from studio_semantic import ProjectScopedSemanticRuntime, SemanticHTTPAdapter, SqliteSemanticStore
from studio_server import (
    LocalServerComposition,
    QualityHTTPAdapter,
    RoninHTTPServer,
    StaticControlPlaneAuthenticator,
    StaticControlPlaneAuthorizer,
    WorkspaceProjectHTTPServer,
)
from studio_sql import ProjectScopedDuckDbSqlEngine, SqlHTTPAdapter
from studio_storage import (
    CompositeSecretResolver,
    EnvironmentSecretResolver,
    LocalArtifactStore,
    PostgresArtifactReferenceBarrier,
    PostgresAuditStore,
    PostgresJobReadPort,
    PostgresMLStore,
    PostgresQualityStore,
    PostgresSchedulerLeadershipStore,
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
from studio_storage.scheduler_backfill_runtime import (
    SchedulerBackfillRuntimePort,
    SchedulerBackfillRuntimeStore,
)
from studio_storage.scheduler_events import SchedulerEventStore
from studio_storage.scheduler_fencing import TaskAttemptId
from studio_storage.scheduler_leadership import SchedulerLeadershipStore
from studio_storage.scheduler_schedule import SchedulerScheduleStore
from studio_streaming import (
    KafkaStreamingHealthReader,
    KafkaStreamingRuntime,
    SqliteStreamCheckpointStore,
)


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


def _seconds(name: str, default: str) -> float:
    try:
        value = float(_env(name, default))
    except ValueError as exc:
        raise ValueError(f"{name} must be a number of seconds") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number of seconds")
    return value


def _workflow_reader_for_backend(
    scheduler: Any, *, now: Instant, postgres_dsn: str | None
) -> Any | None:
    """Expose workflow routes only when the selected store supports every route operation."""
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
        "list_event_deliveries",
        "create_backfill",
        "get_backfill",
        "cancel_backfill",
        "get_run",
        "list_task_runs",
        "create_run",
    )
    if not all(callable(getattr(scheduler, name, None)) for name in required):
        return None
    adapter = PostgresWorkflowHTTPAdapter if postgres_dsn is not None else SqliteWorkflowHTTPAdapter
    return adapter(cast(Any, scheduler), now=now)


def _catalog_reader_for_backend(catalog_store: Any) -> Any | None:
    """Expose catalog routes only when the selected store has their full contract."""
    required = (
        "list_assets",
        "search_assets",
        "list_assets_page",
        "search_assets_page",
        "create_asset",
        "replace_asset",
        "list_revisions",
        "get_revision",
        "upstream",
        "downstream",
        "list_lineage",
        "put_sensitivity",
        "get_sensitivity",
        "list_sensitivity_versions",
        "put_ownership",
        "get_ownership",
        "list_ownership_versions",
    )
    return (
        catalog_store
        if all(callable(getattr(catalog_store, name, None)) for name in required)
        else None
    )


def build_local_composed_from_env() -> LocalServerComposition:
    """Build, but do not start, the opt-in two-surface local profile."""

    database = Path(_env("RONIN_DB", ".ronin/ronin.sqlite3")).expanduser().resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    storage_backend = _env("RONIN_STORAGE_BACKEND", "sqlite").casefold()
    if storage_backend not in {"sqlite", "postgres"}:
        raise ValueError("RONIN_STORAGE_BACKEND must be sqlite or postgres")
    plugin_api_mode = os.environ.get("RONIN_PLUGIN_API", "plugin")
    if plugin_api_mode not in {"legacy", "plugin"}:
        raise ValueError("RONIN_PLUGIN_API must be legacy or plugin")
    plugin_routes_enabled = plugin_api_mode == "plugin"
    host = _env("RONIN_HOST", "127.0.0.1")
    job_port = _port("RONIN_PORT", "8080")
    control_port = _port("RONIN_CONTROL_PLANE_PORT", "8081")
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
    scheduler = (
        PostgresSchedulerSnapshotStore(
            postgres_dsn,
            application_name="ronin-composed-workflows",
        )
        if postgres_dsn is not None
        else SqliteWorkflowBundleImportStore(database, migration_now=now)
    )
    workflow_scheduler = (
        SchedulerBackfillRuntimeStore(database, migration_now=now)
        if postgres_dsn is None
        else scheduler
    )
    scheduler_leadership = (
        PostgresSchedulerLeadershipStore(
            postgres_dsn,
            application_name="ronin-composed-scheduler-leadership",
        )
        if postgres_dsn is not None
        else SchedulerLeadershipStore(database, migration_now=now)
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

    def scheduler_clock() -> Instant:
        return Instant(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))

    def scheduler_work() -> SchedulerDaemonWork:
        active_workspaces = tuple(
            workspace.id for workspace in workspace_service.list() if not workspace.archived
        )
        list_backfills = getattr(workflow_scheduler, "list_active_backfills", None)
        backfills = (
            tuple(
                BackfillTarget(workspace_id, backfill_id)
                for workspace_id in active_workspaces
                for backfill_id in list_backfills(workspace_id, limit=100)
            )
            if callable(list_backfills)
            else ()
        )
        return SchedulerDaemonWork(
            schedule_workspaces=active_workspaces,
            event_workspaces=active_workspaces,
            controller_workspaces=active_workspaces,
            backfills=backfills,
        )

    scheduler_daemon = SchedulerDaemon(
        leadership_store=cast(SchedulerLeadershipStore, scheduler_leadership),
        schedule_store=cast(SchedulerScheduleStore, workflow_scheduler),
        event_store=cast(SchedulerEventStore, workflow_scheduler),
        backfill_store=cast(SchedulerBackfillRuntimePort, workflow_scheduler),
        job_service=job_service,
        owner=_env("RONIN_SCHEDULER_OWNER", f"scheduler-{os.getpid()}"),
        clock=scheduler_clock,
        leader_token_factory=lambda: LeaseToken(secrets.token_urlsafe(32)),
        task_attempt_factory=lambda: TaskAttemptId(f"attempt-{secrets.token_urlsafe(18)}"),
        task_lease_token_factory=lambda: LeaseToken(secrets.token_urlsafe(32)),
    )
    scheduler_service = SchedulerDaemonService(
        scheduler_daemon,
        work_provider=scheduler_work,
        interval_seconds=_seconds("RONIN_SCHEDULER_INTERVAL_SECONDS", "1"),
        retry_seconds=_seconds("RONIN_SCHEDULER_RETRY_SECONDS", "2"),
    )
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
    audit_store = (
        PostgresAuditStore(postgres_dsn, application_name="ronin-composed-audit")
        if postgres_dsn is not None
        else SqliteAuditStore(database, migration_now=now)
    )

    def audit_mutation(
        actor: Actor,
        action: str,
        scoped_workspace_id: WorkspaceId,
        metadata: dict[str, object],
    ) -> None:
        resource_ref = metadata.get("resource", str(scoped_workspace_id))
        event = mutation_audit_event(
            actor,
            workspace_id=str(scoped_workspace_id),
            action=action,
            resource_ref=str(resource_ref),
            metadata=metadata,
            now=scheduler_clock(),
        )
        audit_store.append(scoped_workspace_id, event)

    observability_buffer = LocalObservabilityBuffer()
    ml_lab_store = (
        PostgresMLLabStore(postgres_dsn, application_name="ronin-composed-ml")
        if postgres_dsn is not None
        else SqliteMLLabStore(database, migration_now=now)
    )
    secrets_resolver = CompositeSecretResolver(environment=EnvironmentSecretResolver())
    graph_adapter = (
        OntologyHTTPAdapter(
            cast(Any, SqliteOntologyStore(database, migration_now=now)),
            SqliteKnowledgeGraphStore(database),
        )
        if postgres_dsn is None
        else None
    )
    catalog_reader = _catalog_reader_for_backend(catalog_store)
    configured_sql_parquet_root = os.environ.get("RONIN_SQL_PARQUET_ROOT", "").strip()
    sql_parquet_root = Path(
        configured_sql_parquet_root or database.parent / "sql-parquet"
    ).expanduser()
    sql_engine = ProjectScopedDuckDbSqlEngine(parquet_root=sql_parquet_root)
    sql_reader = SqlHTTPAdapter(sql_engine)
    semantic_reader = None
    try:
        semantic_reader = SemanticHTTPAdapter(
            SqliteSemanticStore(database),
            ProjectScopedSemanticRuntime(sql_engine),
        )
    except Exception as exc:
        if postgres_dsn is None and os.environ.get("RONIN_SEMANTIC_REQUIRED") == "1":
            raise ValueError(f"semantic runtime is required but unavailable: {exc}") from exc
    connection_store = (
        SqliteConnectionStore(database, migration_now=now) if postgres_dsn is None else scheduler
    )
    connection_service = ConnectionService(scheduler, cast(Any, connection_store))
    connector_registry = builtin_connector_registry()
    checkpoint_store = (
        PostgresConnectorCheckpointStore(postgres_dsn)
        if postgres_dsn is not None
        else SqliteConnectorCheckpointStore(database)
    )

    def resolve_connection(scoped_workspace_id: str, reference: str) -> ConnectionDefinition:
        return connection_service.get(WorkspaceId(scoped_workspace_id), ConnectionId(reference))

    streaming_checkpoints = SqliteStreamCheckpointStore(database)
    streaming_health_reader = KafkaStreamingHealthReader(
        streaming_checkpoints,
        resolve_connection,
        lambda reference: secrets_resolver.resolve(reference).reveal_text(),
    )
    streaming_runner = KafkaStreamingRuntime(
        streaming_checkpoints,
        resolve_connection,
        lambda reference: secrets_resolver.resolve(reference).reveal_text(),
        database.parent,
    )

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
        artifact_reference_barrier=artifact_reference_barrier,
    )
    quality_store = (
        SqliteQualityStore(database, migration_now=now)
        if postgres_dsn is None
        else PostgresQualityStore(catalog_store)
    )
    telemetry_store = SqliteTelemetryStore(database)
    telemetry_stores: dict[str, SqliteTelemetryStore] = {str(workspace_id): telemetry_store}
    telemetry_stores_lock = Lock()

    def telemetry_for_workspace(workspace_key: str) -> SqliteTelemetryStore:
        with telemetry_stores_lock:
            store = telemetry_stores.get(workspace_key)
            if store is None:
                digest = sha256(workspace_key.encode("utf-8")).hexdigest()
                store = SqliteTelemetryStore(
                    database.parent
                    / f"{database.stem}.workspace-observability"
                    / f"{digest}.sqlite3"
                )
                telemetry_stores[workspace_key] = store
            return store

    def record_quality_alerts(
        scoped_workspace_id: WorkspaceId, run: QualityRun, observed_at: Instant
    ) -> None:
        workspace_telemetry = telemetry_for_workspace(str(scoped_workspace_id))
        points = record_quality_metrics(run, lambda _point: None, observed_at=observed_at)
        workspace_telemetry.record_quality_metrics_once(
            str(scoped_workspace_id), str(run.id), points
        )
        evaluate_quality_alerts(
            run,
            workspace_telemetry,
            workspace_telemetry.list_alert_rules(),
            observed_at=observed_at,
            record_metric=lambda _point: None,
        )

    quality_reader = QualityHTTPAdapter(quality_store, on_run=record_quality_alerts)
    alert_reader = AlertHTTPAdapter(telemetry_for_workspace)
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
    plugin_host = PluginHost.discover(
        excluded_plugin_ids=frozenset(
            {
                "com.sauronshepherd.ronin.ai-studio",
                "com.sauronshepherd.ronin.genai",
            }
        ),
        services={
            "workspace_service": workspace_service,
            "project_service": project_service,
            "environment_service": environment_service,
            "observability_buffer": observability_buffer,
            "ml_lab_store": ml_lab_store,
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
            "govern_studio_db_path": str(database.parent / "synthetic-data.sqlite3"),
            "catalog_store": catalog_store,
        },
    )
    plugin_host.audit = PluginAuditSink(audit_store.append, workspace_id)
    lock_path = os.environ.get("RONIN_PLUGIN_LOCK")
    if lock_path is not None:
        try:
            lock = PluginLock.read(str(Path(lock_path).expanduser().resolve()))
            plugin_host.verify_lock(lock)
        except (OSError, PluginLockError) as exc:
            with suppress(Exception):
                plugin_host.stop()
            raise ValueError(f"RONIN_PLUGIN_LOCK validation failed: {exc}") from exc

    try:
        job_server = RoninHTTPServer(
            (host, job_port),
            job_service,
            token=_env("RONIN_TOKEN"),
            grants=job_grants,
            migration_router=MigrationAPIRouter(
                MigrationSessionService(SQLiteMigrationSessionStore(database))
            ),
        )
    except Exception:
        with suppress(Exception):
            plugin_host.stop()
        raise
    workflow_http_adapter = _workflow_reader_for_backend(
        workflow_scheduler, now=now, postgres_dsn=postgres_dsn
    )
    control_plane_authorizer = StaticControlPlaneAuthorizer(workspace_id, permissions)
    for known_workspace in workspace_service.list():
        control_plane_authorizer.register_workspace(known_workspace.id)
    try:
        control_server = WorkspaceProjectHTTPServer(
            (host, control_port),
            workspace_service,
            project_service,
            authenticator=StaticControlPlaneAuthenticator(control_token),
            authorizer=control_plane_authorizer,
            workflow_reader=workflow_http_adapter,
            workflow_runner=workflow_http_adapter,
            workflow_canceller=(
                WorkflowCancellationHTTPAdapter(workflow_scheduler, job_service)
                if workflow_http_adapter is not None
                else None
            ),
            graph_query_reader=cast(Any, graph_adapter),
            ontology_reader=graph_adapter,
            catalog_reader=catalog_reader,
            semantic_reader=semantic_reader,
            sql_reader=sql_reader,
            environment_service=environment_service,
            connection_service=connection_service,
            binding_service=binding_service,
            quality_reader=quality_reader,
            alert_reader=alert_reader,
            finops_reader=finops_reader,
            data_engineering_reader=data_engineering_reader,
            streaming_health_reader=streaming_health_reader,
            streaming_runner=cast(Any, streaming_runner),
            notebook_reader=ProjectNotebookHTTPAdapter(),
            feature_definition_service=FeatureDefinitionService(cast(Any, ml_lab_store)),
            connector_registry=connector_registry,
            ingestion_adapter=ingestion_adapter,
            durable_jobs=job_server.application,
            plugin_host=plugin_host,
            plugin_routes_enabled=plugin_routes_enabled,
            default_workspace_id=workspace_id,
            audit_mutation=audit_mutation,
        )
    except Exception:
        if sql_reader is not None:
            sql_reader.close()
        job_server.server_close()
        with suppress(Exception):
            plugin_host.stop()
        raise
    return LocalServerComposition(
        job_server,
        control_server,
        plugin_host=plugin_host,
        background_services=(scheduler_service,),
    )


__all__ = ("build_local_composed_from_env",)
