"""Operator-invoked, fail-closed artifact retention for the local profile."""

from __future__ import annotations

import os
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from studio_connectors import PostgresConnectorCheckpointStore, SqliteConnectorCheckpointStore
from studio_data_engineering import (
    PostgresQueryEvidenceReferenceStore,
    PostgresRevisionStore,
    SqliteQueryEvidenceReferenceStore,
)
from studio_data_engineering.sqlite_revisions import SqliteRevisionStore
from studio_orchestrator import Instant
from studio_runtime import PluginHost
from studio_storage import (
    ArtifactRetentionPlan,
    LocalArtifactStore,
    PostgresArtifactReferenceBarrier,
    PostgresJobReadPort,
    PostgresMLStore,
    PostgresSchedulerSnapshotStore,
    SqliteCatalogStore,
    SqliteJobStore,
    collect_referenced_artifacts,
    discover_artifact_references,
    plan_unreferenced,
)
from studio_storage.bundle_workflow_import import SqliteWorkflowBundleImportStore
from studio_storage.ml import SqliteMLStore

_REVIEWED_PLUGIN_IDS = frozenset(
    {
        "com.ronin.synthetic-data-studio",
        "com.sauronshepherd.ronin.cloud-studio",
        "com.sauronshepherd.ronin.logging",
        "com.sauronshepherd.ronin.ml-studio",
        "com.sauronshepherd.ronin.monitoring",
        "com.sauronshepherd.ronin.workspaces",
    }
)


def _unreviewed_plugins(host: PluginHost) -> tuple[str, ...]:
    if host.plan is None:
        return ("plugin-inventory-unavailable",)
    return tuple(
        sorted(
            record.manifest.id
            for record in host.plan.records
            if record.manifest.id not in _REVIEWED_PLUGIN_IDS
        )
    )


@dataclass(slots=True)
class _RetentionStores:
    artifact_store: LocalArtifactStore
    workspaces: Any
    catalog: Any
    ml_registry: Any
    jobs: Any
    connector_checkpoints: Any
    data_engineering_revisions: Any
    query_evidence: Any
    synthetic_exports: Any
    barrier: PostgresArtifactReferenceBarrier | None
    plugin_host: PluginHost
    unreviewed_plugins: tuple[str, ...]

    def close(self) -> None:
        self.plugin_host.stop()


def _synthetic_exports(database_path: Path) -> tuple[PluginHost, Any, tuple[str, ...]]:
    host = PluginHost.discover(services={"govern_studio_db_path": str(database_path)})
    if host.plan is None:
        host.stop()
        raise ValueError("artifact retention could not compose built-in reference stores")
    record = next(
        (
            record
            for record in host.plan.records
            if record.manifest.id == "com.ronin.synthetic-data-studio"
        ),
        None,
    )
    service = None if record is None else getattr(record.plugin, "service", None)
    if not all(callable(getattr(service, name, None)) for name in ("snapshot", "artifacts")):
        host.stop()
        raise ValueError("synthetic export reference store is unavailable")
    return host, service, _unreviewed_plugins(host)


def _stores_from_environment() -> tuple[_RetentionStores, str]:
    database = Path(os.environ.get("RONIN_DB", ".ronin/ronin.sqlite3")).expanduser().resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    backend = os.environ.get("RONIN_STORAGE_BACKEND", "sqlite").strip().casefold()
    if backend not in {"sqlite", "postgres"}:
        raise ValueError("RONIN_STORAGE_BACKEND must be sqlite or postgres")
    now = Instant("2026-09-17T00:00:00.000000Z")
    ml_registry: Any
    jobs: Any
    connector_checkpoints: Any
    data_engineering_revisions: Any
    query_evidence: Any

    if backend == "postgres":
        dsn = os.environ.get("RONIN_POSTGRES_DSN")
        if not dsn or dsn != dsn.strip():
            raise ValueError("RONIN_POSTGRES_DSN is required and must be non-empty and trimmed")
        workspace_catalog = PostgresSchedulerSnapshotStore(
            dsn, application_name="ronin-artifact-retention-metadata"
        )
        artifact_store = LocalArtifactStore(database.parent / "artifacts")
        ml_registry = PostgresMLStore(dsn, application_name="ronin-artifact-retention-ml")
        jobs = PostgresJobReadPort(dsn, application_name="ronin-artifact-retention-jobs")
        connector_checkpoints = PostgresConnectorCheckpointStore(
            dsn, application_name="ronin-artifact-retention-connectors"
        )
        data_engineering_revisions = PostgresRevisionStore(
            dsn, application_name="ronin-artifact-retention-revisions"
        )
        query_evidence = PostgresQueryEvidenceReferenceStore(
            dsn, application_name="ronin-artifact-retention-query-evidence"
        )
        barrier = PostgresArtifactReferenceBarrier(
            dsn, application_name="ronin-artifact-retention-collector"
        )
        plugin_host, synthetic_exports, unreviewed_plugins = _synthetic_exports(
            database.parent / "synthetic-data.sqlite3"
        )
        stores = _RetentionStores(
            artifact_store,
            workspace_catalog,
            workspace_catalog,
            ml_registry,
            jobs,
            connector_checkpoints,
            data_engineering_revisions,
            query_evidence,
            synthetic_exports,
            barrier,
            plugin_host,
            unreviewed_plugins,
        )
        return stores, backend

    workspace_store = SqliteWorkflowBundleImportStore(database, migration_now=now)
    artifact_store = LocalArtifactStore(database.parent / "artifacts")
    catalog = SqliteCatalogStore(database, migration_now=now)
    ml_registry = SqliteMLStore(database, migration_now=now)
    jobs = SqliteJobStore(database, migration_now=now)
    connector_checkpoints = SqliteConnectorCheckpointStore(database)
    data_engineering_revisions = SqliteRevisionStore(database)
    query_evidence = SqliteQueryEvidenceReferenceStore(database)
    plugin_host, synthetic_exports, unreviewed_plugins = _synthetic_exports(
        database.parent / "synthetic-data.sqlite3"
    )
    stores = _RetentionStores(
        artifact_store,
        workspace_store,
        catalog,
        ml_registry,
        jobs,
        connector_checkpoints,
        data_engineering_revisions,
        query_evidence,
        synthetic_exports,
        None,
        plugin_host,
        unreviewed_plugins,
    )
    return stores, backend


def run_artifact_retention(
    mode: str,
    *,
    confirmed: bool = False,
    allow_empty_live_set: bool = False,
    page_size: int = 500,
    max_objects: int = 10_000,
    max_pages: int = 1_000,
) -> dict[str, object]:
    """Preview known stale artifacts or explicitly collect them in PostgreSQL mode."""

    if mode not in {"preview", "collect"}:
        raise ValueError("artifact retention mode must be preview or collect")
    if not isinstance(confirmed, bool):
        raise ValueError("confirmed must be a boolean")
    if not isinstance(allow_empty_live_set, bool):
        raise ValueError("allow_empty_live_set must be a boolean")
    if mode == "collect" and not confirmed:
        raise ValueError("artifact collection requires the explicit --confirm flag")
    if mode == "preview" and allow_empty_live_set:
        raise ValueError("--allow-empty-live-set is only valid with collect")
    requested_backend = os.environ.get("RONIN_STORAGE_BACKEND", "sqlite").strip().casefold()
    if mode == "collect" and requested_backend != "postgres":
        raise ValueError(
            "artifact collection requires RONIN_STORAGE_BACKEND=postgres so writers "
            "and the collector share the PostgreSQL barrier"
        )

    stores, backend = _stores_from_environment()
    try:
        if mode == "collect":
            if stores.barrier is None:
                raise ValueError(
                    "artifact collection requires RONIN_STORAGE_BACKEND=postgres so writers "
                    "and the collector share the PostgreSQL barrier"
                )
            if stores.unreviewed_plugins:
                raise ValueError(
                    "artifact collection is blocked by unreviewed plugins: "
                    + ", ".join(stores.unreviewed_plugins)
                )
            deleted = collect_referenced_artifacts(
                stores.barrier,
                stores.artifact_store,
                stores.workspaces,
                stores.catalog,
                stores.ml_registry,
                stores.jobs,
                stores.connector_checkpoints,
                stores.data_engineering_revisions,
                stores.query_evidence,
                stores.synthetic_exports,
                allow_empty_live_set=allow_empty_live_set,
                page_size=page_size,
                max_objects=max_objects,
                max_pages=max_pages,
            )
            return {
                "schema": "ronin.artifact-retention-result/v1",
                "mode": mode,
                "backend": backend,
                "snapshot_consistent": True,
                "collection_ready": True,
                "deleted_digests": list(deleted),
                "deleted_count": len(deleted),
            }

        guard = stores.barrier.collector() if stores.barrier is not None else nullcontext()
        with guard:
            references = discover_artifact_references(
                stores.workspaces,
                stores.catalog,
                stores.ml_registry,
                stores.jobs,
                stores.connector_checkpoints,
                stores.data_engineering_revisions,
                stores.query_evidence,
                stores.synthetic_exports,
            )
            plan: ArtifactRetentionPlan = plan_unreferenced(
                stores.artifact_store,
                references,
                page_size=page_size,
                max_objects=max_objects,
                max_pages=max_pages,
            )
        live_reference_count = sum(len(digests) for digests in references.values())
        return {
            "schema": "ronin.artifact-retention-result/v1",
            "mode": mode,
            "backend": backend,
            "snapshot_consistent": stores.barrier is not None,
            "live_reference_count": live_reference_count,
            "candidate_digests": list(plan.candidate_digests),
            "missing_sources": list(plan.missing_sources),
            "inventory_truncated": plan.inventory_truncated,
            "collection_ready": (
                stores.barrier is not None
                and not stores.unreviewed_plugins
                and not plan.missing_sources
                and not plan.inventory_truncated
                and live_reference_count > 0
            ),
            "unreviewed_plugins": list(stores.unreviewed_plugins),
        }
    finally:
        stores.close()


__all__ = ("run_artifact_retention",)
