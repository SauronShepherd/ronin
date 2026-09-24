"""PostgreSQL metadata adapter for core Public v1 control-plane domains.

This adapter implements the existing provider-neutral Workspace, Environment,
Connection and Catalog store contracts without exposing SQL/ORM primitives to
application services. JSON payloads remain the canonical domain serialization;
PostgreSQL supplies shared multi-process durability and transactional semantics.
"""

from __future__ import annotations

from typing import Any

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

from .bundle_catalog_import_port import CatalogBundleImportCommit, CatalogBundleImportConflict
from .bundle_multi_import_port import MultiObjectBundleImportCommit, MultiObjectBundleImportConflict
from .catalog import CatalogAssetNotFound, CatalogConflict
from .connections import ConnectionConflict, ConnectionNotFound
from .environments import EnvironmentConflict, EnvironmentNotFound
from .workspaces import (
    ProjectRegistrationConflict,
    WorkspaceConflict,
    WorkspaceNotFound,
)


class PostgresDependencyError(RuntimeError):
    """Raised when psycopg is not installed for the server metadata profile."""


def _psycopg() -> tuple[Any, Any]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise PostgresDependencyError(
            "PostgreSQL metadata support requires psycopg from Ronin data-plane/server dependencies"
        ) from exc
    return psycopg, dict_row


_SCHEMA = """
CREATE TABLE IF NOT EXISTS ronin_workspaces (
    workspace_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version BIGINT NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS ronin_projects (
    workspace_id TEXT NOT NULL REFERENCES ronin_workspaces(workspace_id) ON DELETE CASCADE,
    project_id TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    row_version BIGINT NOT NULL DEFAULT 1,
    PRIMARY KEY(workspace_id, project_id)
);
CREATE TABLE IF NOT EXISTS ronin_environments (
    workspace_id TEXT NOT NULL REFERENCES ronin_workspaces(workspace_id) ON DELETE CASCADE,
    environment_id TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version BIGINT NOT NULL DEFAULT 1,
    PRIMARY KEY(workspace_id, environment_id)
);
CREATE TABLE IF NOT EXISTS ronin_project_environment_bindings (
    workspace_id TEXT NOT NULL REFERENCES ronin_workspaces(workspace_id) ON DELETE CASCADE,
    project_id TEXT NOT NULL,
    environment_id TEXT NOT NULL,
    bindings_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version BIGINT NOT NULL DEFAULT 1,
    PRIMARY KEY(workspace_id, project_id, environment_id),
    FOREIGN KEY(workspace_id, project_id)
        REFERENCES ronin_projects(workspace_id, project_id) ON DELETE CASCADE,
    FOREIGN KEY(workspace_id, environment_id)
        REFERENCES ronin_environments(workspace_id, environment_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS ronin_connections (
    workspace_id TEXT NOT NULL REFERENCES ronin_workspaces(workspace_id) ON DELETE CASCADE,
    connection_id TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version BIGINT NOT NULL DEFAULT 1,
    PRIMARY KEY(workspace_id, connection_id)
);
CREATE TABLE IF NOT EXISTS ronin_catalog_assets (
    workspace_id TEXT NOT NULL REFERENCES ronin_workspaces(workspace_id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version BIGINT NOT NULL DEFAULT 1,
    PRIMARY KEY(workspace_id, asset_id)
);
CREATE TABLE IF NOT EXISTS ronin_catalog_revisions (
    workspace_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    version TEXT NOT NULL,
    revision_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(workspace_id, asset_id, version),
    FOREIGN KEY(workspace_id, asset_id)
        REFERENCES ronin_catalog_assets(workspace_id, asset_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS ronin_lineage_edges (
    workspace_id TEXT NOT NULL REFERENCES ronin_workspaces(workspace_id) ON DELETE CASCADE,
    edge_digest TEXT NOT NULL,
    source_asset_id TEXT NOT NULL,
    source_version TEXT NOT NULL,
    target_asset_id TEXT NOT NULL,
    target_version TEXT NOT NULL,
    edge_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(workspace_id, edge_digest)
);
CREATE INDEX IF NOT EXISTS ronin_lineage_source_idx
    ON ronin_lineage_edges(workspace_id, source_asset_id, source_version);
CREATE INDEX IF NOT EXISTS ronin_lineage_target_idx
    ON ronin_lineage_edges(workspace_id, target_asset_id, target_version);
CREATE TABLE IF NOT EXISTS ronin_jobs (
    job_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    state TEXT NOT NULL,
    failure_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version BIGINT NOT NULL DEFAULT 0,
    target TEXT NOT NULL DEFAULT '',
    parameters_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(project_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS ronin_runs (
    run_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES ronin_jobs(job_id) ON DELETE CASCADE,
    ordinal BIGINT NOT NULL,
    state TEXT NOT NULL,
    not_before TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version BIGINT NOT NULL DEFAULT 0,
    UNIQUE(job_id, ordinal)
);
CREATE TABLE IF NOT EXISTS ronin_attempts (
    attempt_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES ronin_runs(run_id) ON DELETE CASCADE,
    ordinal BIGINT NOT NULL,
    state TEXT NOT NULL,
    lease_owner TEXT,
    lease_token TEXT,
    lease_expires_at TEXT,
    heartbeat_at TEXT,
    failure_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version BIGINT NOT NULL DEFAULT 0,
    UNIQUE(run_id, ordinal)
);
CREATE TABLE IF NOT EXISTS ronin_attempt_events (
    attempt_id TEXT NOT NULL REFERENCES ronin_attempts(attempt_id) ON DELETE CASCADE,
    sequence BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    PRIMARY KEY (attempt_id, sequence)
);
CREATE TABLE IF NOT EXISTS ronin_cell_results (
    run_id TEXT NOT NULL REFERENCES ronin_runs(run_id) ON DELETE CASCADE,
    cell_id TEXT NOT NULL,
    source_digest TEXT NOT NULL,
    execution_identity_digest TEXT NOT NULL,
    state TEXT NOT NULL,
    result_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (run_id, cell_id)
);
CREATE TABLE IF NOT EXISTS ronin_evidence_refs (
    evidence_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES ronin_runs(run_id) ON DELETE CASCADE,
    cell_id TEXT,
    role TEXT NOT NULL,
    digest_algorithm TEXT,
    digest TEXT,
    media_type TEXT,
    size_bytes BIGINT,
    storage_ref TEXT,
    availability TEXT NOT NULL DEFAULT 'available',
    unavailable_reason TEXT,
    CHECK (availability IN ('available', 'missing', 'tombstoned', 'unavailable')),
    CHECK (
        (availability = 'unavailable'
            AND digest_algorithm IS NULL AND digest IS NULL
            AND size_bytes IS NULL AND storage_ref IS NULL
            AND unavailable_reason IS NOT NULL)
        OR
        (availability <> 'unavailable'
            AND digest_algorithm IS NOT NULL AND digest IS NOT NULL
            AND size_bytes IS NOT NULL AND unavailable_reason IS NULL)
    )
);
CREATE INDEX IF NOT EXISTS ronin_runs_claimable_idx
    ON ronin_runs(state, not_before, run_id);
CREATE INDEX IF NOT EXISTS ronin_attempts_expiry_idx
    ON ronin_attempts(state, lease_expires_at);
CREATE INDEX IF NOT EXISTS ronin_runs_job_idx
    ON ronin_runs(job_id, ordinal);
CREATE INDEX IF NOT EXISTS ronin_attempts_run_idx
    ON ronin_attempts(run_id, ordinal);
CREATE TABLE IF NOT EXISTS ronin_workflows (
    workspace_id TEXT NOT NULL REFERENCES ronin_workspaces(workspace_id) ON DELETE CASCADE,
    workflow_id TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(workspace_id, workflow_id)
);
CREATE TABLE IF NOT EXISTS ronin_schedules (
    workspace_id TEXT NOT NULL REFERENCES ronin_workspaces(workspace_id) ON DELETE CASCADE,
    schedule_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    schedule_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(workspace_id, schedule_id),
    FOREIGN KEY(workspace_id, workflow_id)
        REFERENCES ronin_workflows(workspace_id, workflow_id) ON DELETE CASCADE
);
"""


class PostgresMetadataStore:
    """Shared PostgreSQL adapter for workspace/environment/connection/catalog metadata."""

    def __init__(self, dsn: str, *, application_name: str = "ronin") -> None:
        if not dsn or dsn != dsn.strip():
            raise ValueError("PostgreSQL DSN must be non-empty and trimmed")
        if not application_name or application_name != application_name.strip():
            raise ValueError("application_name must be non-empty and trimmed")
        self._dsn = dsn
        self._application_name = application_name
        self.migrate()

    def _connect(self) -> Any:
        psycopg, dict_row = _psycopg()
        return psycopg.connect(
            self._dsn,
            autocommit=False,
            row_factory=dict_row,
            application_name=self._application_name,
        )

    def migrate(self) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(_SCHEMA)
                cursor.execute(
                    "ALTER TABLE ronin_projects ADD COLUMN IF NOT EXISTS archived_at TEXT"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def ready(self) -> bool:
        """Probe PostgreSQL without exposing connection details to callers."""
        try:
            connection = self._connect()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    return cursor.fetchone() is not None
            finally:
                connection.close()
        except Exception:
            return False

    @staticmethod
    def _workspace_from_row(row: dict[str, object]) -> Workspace:
        return Workspace(
            WorkspaceId(str(row["workspace_id"])),
            str(row["name"]),
            None if row["description"] is None else str(row["description"]),
            "archived" if row["archived_at"] is not None else "active",
        )

    @staticmethod
    def _require_active_workspace(cursor: Any, workspace_id: WorkspaceId) -> None:
        cursor.execute(
            "SELECT archived_at FROM ronin_workspaces WHERE workspace_id=%s",
            (str(workspace_id),),
        )
        row = cursor.fetchone()
        if row is None:
            raise WorkspaceNotFound(str(workspace_id))
        if row["archived_at"] is not None:
            raise WorkspaceConflict("cannot mutate metadata in an archived workspace")

    # WorkspaceStore
    def create_workspace(self, workspace: Workspace, *, now: Instant | str) -> Workspace:
        if workspace.archived:
            raise ValueError("new workspace must be active")
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM ronin_workspaces WHERE workspace_id=%s FOR UPDATE",
                    (str(workspace.id),),
                )
                row = cursor.fetchone()
                if row is not None:
                    existing = self._workspace_from_row(row)
                    if existing == workspace:
                        connection.commit()
                        return existing
                    raise WorkspaceConflict(f"workspace id already exists: {workspace.id}")
                cursor.execute(
                    "INSERT INTO ronin_workspaces("
                    "workspace_id,name,description,archived_at,created_at,updated_at) "
                    "VALUES (%s,%s,%s,NULL,%s,%s)",
                    (
                        str(workspace.id),
                        workspace.name,
                        workspace.description,
                        str(current),
                        str(current),
                    ),
                )
            connection.commit()
            return workspace
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_workspace(self, workspace_id: WorkspaceId) -> Workspace | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM ronin_workspaces WHERE workspace_id=%s",
                    (str(workspace_id),),
                )
                row = cursor.fetchone()
                return None if row is None else self._workspace_from_row(row)
        finally:
            connection.close()

    def list_workspaces(self) -> tuple[Workspace, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM ronin_workspaces ORDER BY workspace_id")
                return tuple(self._workspace_from_row(row) for row in cursor.fetchall())
        finally:
            connection.close()

    def update_workspace(self, workspace: Workspace, *, now: Instant | str) -> Workspace:
        current = Instant(now)
        archived_at = str(current) if workspace.archived else None
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE ronin_workspaces SET name=%s,description=%s,archived_at=%s,"
                    "updated_at=%s,"
                    "row_version=row_version+1 WHERE workspace_id=%s",
                    (
                        workspace.name,
                        workspace.description,
                        archived_at,
                        str(current),
                        str(workspace.id),
                    ),
                )
                if cursor.rowcount != 1:
                    raise WorkspaceNotFound(str(workspace.id))
            connection.commit()
            return workspace
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def register_project(
        self, workspace_id: WorkspaceId, manifest: ProjectManifest, *, now: Instant | str
    ) -> ProjectManifest:
        current = Instant(now)
        payload = manifest.to_json()
        project_id = manifest.project.id
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_active_workspace(cursor, workspace_id)
                cursor.execute(
                    "SELECT manifest_json FROM ronin_projects "
                    "WHERE workspace_id=%s AND project_id=%s FOR UPDATE",
                    (str(workspace_id), str(project_id)),
                )
                row = cursor.fetchone()
                if row is not None:
                    if row["manifest_json"] == payload:
                        connection.commit()
                        return manifest
                    raise ProjectRegistrationConflict(
                        f"project registration already exists with different intent: {project_id}"
                    )
                cursor.execute(
                    "INSERT INTO ronin_projects("
                    "workspace_id,project_id,manifest_json,created_at,updated_at) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (str(workspace_id), str(project_id), payload, str(current), str(current)),
                )
            connection.commit()
            return manifest
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def replace_project(
        self, workspace_id: WorkspaceId, manifest: ProjectManifest, *, now: Instant | str
    ) -> ProjectManifest:
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_active_workspace(cursor, workspace_id)
                cursor.execute(
                    "UPDATE ronin_projects SET manifest_json=%s,updated_at=%s, "
                    "row_version=row_version+1 "
                    "WHERE workspace_id=%s AND project_id=%s",
                    (manifest.to_json(), str(current), str(workspace_id), str(manifest.project.id)),
                )
                if cursor.rowcount != 1:
                    raise KeyError(f"{workspace_id}/{manifest.project.id}")
            connection.commit()
            return manifest
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_project(
        self, workspace_id: WorkspaceId, project_id: ProjectId
    ) -> ProjectManifest | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT manifest_json FROM ronin_projects "
                    "WHERE workspace_id=%s AND project_id=%s",
                    (str(workspace_id), str(project_id)),
                )
                row = cursor.fetchone()
                return None if row is None else ProjectManifest.from_json(row["manifest_json"])
        finally:
            connection.close()

    def list_projects(self, workspace_id: WorkspaceId) -> tuple[ProjectManifest, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT manifest_json FROM ronin_projects "
                    "WHERE workspace_id=%s AND archived_at IS NULL ORDER BY project_id",
                    (str(workspace_id),),
                )
                return tuple(
                    ProjectManifest.from_json(row["manifest_json"]) for row in cursor.fetchall()
                )
        finally:
            connection.close()

    def archive_project(
        self, workspace_id: WorkspaceId, project_id: ProjectId, *, now: Instant | str
    ) -> bool:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_active_workspace(cursor, workspace_id)
                cursor.execute(
                    "UPDATE ronin_projects SET archived_at=%s,updated_at=%s,"
                    "row_version=row_version+1 "
                    "WHERE workspace_id=%s AND project_id=%s AND archived_at IS NULL",
                    (str(Instant(now)), str(Instant(now)), str(workspace_id), str(project_id)),
                )
                archived = bool(cursor.rowcount == 1)
            connection.commit()
            return archived
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def unregister_project(self, workspace_id: WorkspaceId, project_id: ProjectId) -> bool:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_active_workspace(cursor, workspace_id)
                cursor.execute(
                    "DELETE FROM ronin_projects WHERE workspace_id=%s AND project_id=%s",
                    (str(workspace_id), str(project_id)),
                )
                deleted = bool(cursor.rowcount == 1)
            connection.commit()
            return deleted
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # EnvironmentStore
    def put_environment(
        self,
        workspace_id: WorkspaceId,
        environment: EnvironmentDefinition,
        *,
        now: Instant | str,
    ) -> EnvironmentDefinition:
        current = Instant(now)
        payload = environment.to_json()
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_active_workspace(cursor, workspace_id)
                cursor.execute(
                    "INSERT INTO ronin_environments("
                    "workspace_id,environment_id,definition_json,created_at,updated_at) "
                    "VALUES (%s,%s,%s,%s,%s) "
                    "ON CONFLICT(workspace_id,environment_id) DO UPDATE SET "
                    "definition_json=EXCLUDED.definition_json,updated_at=EXCLUDED.updated_at,"
                    "row_version=ronin_environments.row_version+1",
                    (str(workspace_id), str(environment.id), payload, str(current), str(current)),
                )
            connection.commit()
            return environment
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_environment(
        self, workspace_id: WorkspaceId, environment_id: EnvironmentId
    ) -> EnvironmentDefinition | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT definition_json FROM ronin_environments "
                    "WHERE workspace_id=%s AND environment_id=%s",
                    (str(workspace_id), str(environment_id)),
                )
                row = cursor.fetchone()
                return (
                    None if row is None else EnvironmentDefinition.from_json(row["definition_json"])
                )
        finally:
            connection.close()

    def list_environments(self, workspace_id: WorkspaceId) -> tuple[EnvironmentDefinition, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT definition_json FROM ronin_environments "
                    "WHERE workspace_id=%s ORDER BY environment_id",
                    (str(workspace_id),),
                )
                return tuple(
                    EnvironmentDefinition.from_json(row["definition_json"])
                    for row in cursor.fetchall()
                )
        finally:
            connection.close()

    def put_project_bindings(
        self,
        workspace_id: WorkspaceId,
        bindings: ProjectEnvironmentBindings,
        *,
        now: Instant | str,
    ) -> ProjectEnvironmentBindings:
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_active_workspace(cursor, workspace_id)
                cursor.execute(
                    "SELECT 1 FROM ronin_projects WHERE workspace_id=%s AND project_id=%s",
                    (str(workspace_id), str(bindings.project_id)),
                )
                if cursor.fetchone() is None:
                    raise KeyError(f"project not registered: {bindings.project_id}")
                cursor.execute(
                    "SELECT definition_json FROM ronin_environments "
                    "WHERE workspace_id=%s AND environment_id=%s",
                    (str(workspace_id), str(bindings.environment_id)),
                )
                row = cursor.fetchone()
                if row is None:
                    raise EnvironmentNotFound(str(bindings.environment_id))
                if EnvironmentDefinition.from_json(row["definition_json"]).disabled:
                    raise EnvironmentConflict("cannot bind a project to a disabled environment")
                cursor.execute(
                    "INSERT INTO ronin_project_environment_bindings("
                    "workspace_id,project_id,environment_id,bindings_json,created_at,updated_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT(workspace_id,project_id,environment_id) DO UPDATE SET "
                    "bindings_json=EXCLUDED.bindings_json,updated_at=EXCLUDED.updated_at,"
                    "row_version=ronin_project_environment_bindings.row_version+1",
                    (
                        str(workspace_id),
                        str(bindings.project_id),
                        str(bindings.environment_id),
                        bindings.to_json(),
                        str(current),
                        str(current),
                    ),
                )
            connection.commit()
            return bindings
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_project_bindings(
        self,
        workspace_id: WorkspaceId,
        project_id: ProjectId,
        environment_id: EnvironmentId,
    ) -> ProjectEnvironmentBindings | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT bindings_json FROM ronin_project_environment_bindings "
                    "WHERE workspace_id=%s AND project_id=%s AND environment_id=%s",
                    (str(workspace_id), str(project_id), str(environment_id)),
                )
                row = cursor.fetchone()
                return (
                    None
                    if row is None
                    else ProjectEnvironmentBindings.from_json(row["bindings_json"])
                )
        finally:
            connection.close()

    # ConnectionStore
    def create_connection(
        self, workspace_id: WorkspaceId, definition: ConnectionDefinition, *, now: Instant | str
    ) -> ConnectionDefinition:
        current = Instant(now)
        payload = definition.to_json()
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_active_workspace(cursor, workspace_id)
                cursor.execute(
                    "SELECT definition_json FROM ronin_connections "
                    "WHERE workspace_id=%s AND connection_id=%s FOR UPDATE",
                    (str(workspace_id), str(definition.id)),
                )
                row = cursor.fetchone()
                if row is not None:
                    if row["definition_json"] == payload:
                        connection.commit()
                        return definition
                    raise ConnectionConflict(f"connection id already exists: {definition.id}")
                cursor.execute(
                    "INSERT INTO ronin_connections("
                    "workspace_id,connection_id,definition_json,created_at,updated_at) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (str(workspace_id), str(definition.id), payload, str(current), str(current)),
                )
            connection.commit()
            return definition
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def replace_connection(
        self, workspace_id: WorkspaceId, definition: ConnectionDefinition, *, now: Instant | str
    ) -> ConnectionDefinition:
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_active_workspace(cursor, workspace_id)
                cursor.execute(
                    "UPDATE ronin_connections SET definition_json=%s,updated_at=%s, "
                    "row_version=row_version+1 "
                    "WHERE workspace_id=%s AND connection_id=%s",
                    (definition.to_json(), str(current), str(workspace_id), str(definition.id)),
                )
                if cursor.rowcount != 1:
                    raise ConnectionNotFound(str(definition.id))
            connection.commit()
            return definition
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_connection(
        self, workspace_id: WorkspaceId, connection_id: ConnectionId
    ) -> ConnectionDefinition | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT definition_json FROM ronin_connections "
                    "WHERE workspace_id=%s AND connection_id=%s",
                    (str(workspace_id), str(connection_id)),
                )
                row = cursor.fetchone()
                return (
                    None if row is None else ConnectionDefinition.from_json(row["definition_json"])
                )
        finally:
            connection.close()

    def list_connections(self, workspace_id: WorkspaceId) -> tuple[ConnectionDefinition, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT definition_json FROM ronin_connections "
                    "WHERE workspace_id=%s ORDER BY connection_id",
                    (str(workspace_id),),
                )
                return tuple(
                    ConnectionDefinition.from_json(row["definition_json"])
                    for row in cursor.fetchall()
                )
        finally:
            connection.close()

    def delete_connection(self, workspace_id: WorkspaceId, connection_id: ConnectionId) -> bool:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_active_workspace(cursor, workspace_id)
                cursor.execute(
                    "DELETE FROM ronin_connections WHERE workspace_id=%s AND connection_id=%s",
                    (str(workspace_id), str(connection_id)),
                )
                deleted = bool(cursor.rowcount == 1)
            connection.commit()
            return deleted
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # CatalogStore
    def create_asset(
        self, workspace_id: WorkspaceId, asset: CatalogAsset, *, now: Instant | str
    ) -> CatalogAsset:
        current = Instant(now)
        payload = asset.to_json()
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_active_workspace(cursor, workspace_id)
                cursor.execute(
                    "SELECT definition_json FROM ronin_catalog_assets "
                    "WHERE workspace_id=%s AND asset_id=%s FOR UPDATE",
                    (str(workspace_id), str(asset.id)),
                )
                row = cursor.fetchone()
                if row is not None:
                    if row["definition_json"] == payload:
                        connection.commit()
                        return asset
                    raise CatalogConflict(f"catalog asset id already exists: {asset.id}")
                cursor.execute(
                    "INSERT INTO ronin_catalog_assets("
                    "workspace_id,asset_id,definition_json,created_at,updated_at) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (str(workspace_id), str(asset.id), payload, str(current), str(current)),
                )
            connection.commit()
            return asset
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def replace_asset(
        self, workspace_id: WorkspaceId, asset: CatalogAsset, *, now: Instant | str
    ) -> CatalogAsset:
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_active_workspace(cursor, workspace_id)
                cursor.execute(
                    "UPDATE ronin_catalog_assets SET definition_json=%s,updated_at=%s, "
                    "row_version=row_version+1 "
                    "WHERE workspace_id=%s AND asset_id=%s",
                    (asset.to_json(), str(current), str(workspace_id), str(asset.id)),
                )
                if cursor.rowcount != 1:
                    raise CatalogAssetNotFound(str(asset.id))
            connection.commit()
            return asset
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_asset(self, workspace_id: WorkspaceId, asset_id: AssetId) -> CatalogAsset | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT definition_json FROM ronin_catalog_assets "
                    "WHERE workspace_id=%s AND asset_id=%s",
                    (str(workspace_id), str(asset_id)),
                )
                row = cursor.fetchone()
                return None if row is None else CatalogAsset.from_json(row["definition_json"])
        finally:
            connection.close()

    def list_assets(self, workspace_id: WorkspaceId) -> tuple[CatalogAsset, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT definition_json FROM ronin_catalog_assets "
                    "WHERE workspace_id=%s ORDER BY asset_id",
                    (str(workspace_id),),
                )
                return tuple(
                    CatalogAsset.from_json(row["definition_json"]) for row in cursor.fetchall()
                )
        finally:
            connection.close()

    def healthcheck(self) -> bool:
        """Verify connectivity and transaction usability without mutating data."""
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
            connection.rollback()
            return bool(row is not None and str(row[0]) == "1")
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def search_assets(
        self, workspace_id: WorkspaceId, query: str, *, limit: int = 100
    ) -> tuple[CatalogAsset, ...]:
        term = query.strip().casefold()
        if not term:
            raise ValueError("catalog search query must not be empty")
        if limit < 1 or limit > 1_000:
            raise ValueError("catalog search limit must be between 1 and 1000")
        matches = []
        for asset in self.list_assets(workspace_id):
            haystack = " ".join(
                (str(asset.id), asset.kind, asset.name, *asset.tags, *asset.classifications)
            ).casefold()
            if term in haystack:
                matches.append(asset)
        return tuple(matches[:limit])

    def put_revision(
        self, workspace_id: WorkspaceId, revision: AssetRevision, *, now: Instant | str
    ) -> AssetRevision:
        current = Instant(now)
        payload = revision.to_json()
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_active_workspace(cursor, workspace_id)
                cursor.execute(
                    "SELECT 1 FROM ronin_catalog_assets WHERE workspace_id=%s AND asset_id=%s",
                    (str(workspace_id), str(revision.ref.asset_id)),
                )
                if cursor.fetchone() is None:
                    raise CatalogAssetNotFound(str(revision.ref.asset_id))
                cursor.execute(
                    "SELECT revision_json FROM ronin_catalog_revisions "
                    "WHERE workspace_id=%s AND asset_id=%s AND version=%s FOR UPDATE",
                    (str(workspace_id), str(revision.ref.asset_id), str(revision.ref.version)),
                )
                row = cursor.fetchone()
                if row is not None and row["revision_json"] != payload:
                    raise CatalogConflict(
                        "asset revision identity already exists with different metadata"
                    )
                if row is None:
                    cursor.execute(
                        "INSERT INTO ronin_catalog_revisions("
                        "workspace_id,asset_id,version,revision_json,created_at) "
                        "VALUES (%s,%s,%s,%s,%s)",
                        (
                            str(workspace_id),
                            str(revision.ref.asset_id),
                            str(revision.ref.version),
                            payload,
                            str(current),
                        ),
                    )
            connection.commit()
            return revision
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_revision(self, workspace_id: WorkspaceId, ref: AssetRef) -> AssetRevision | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT revision_json FROM ronin_catalog_revisions "
                    "WHERE workspace_id=%s AND asset_id=%s AND version=%s",
                    (str(workspace_id), str(ref.asset_id), str(ref.version)),
                )
                row = cursor.fetchone()
                return None if row is None else AssetRevision.from_json(row["revision_json"])
        finally:
            connection.close()

    def put_lineage(
        self, workspace_id: WorkspaceId, edge: LineageEdge, *, now: Instant | str
    ) -> LineageEdge:
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_active_workspace(cursor, workspace_id)
                for ref in (edge.source, edge.target):
                    cursor.execute(
                        "SELECT 1 FROM ronin_catalog_revisions "
                        "WHERE workspace_id=%s AND asset_id=%s AND version=%s",
                        (str(workspace_id), str(ref.asset_id), str(ref.version)),
                    )
                    if cursor.fetchone() is None:
                        raise CatalogAssetNotFound(f"{ref.asset_id}@{ref.version}")
                cursor.execute(
                    "SELECT edge_json FROM ronin_lineage_edges "
                    "WHERE workspace_id=%s AND edge_digest=%s FOR UPDATE",
                    (str(workspace_id), edge.digest),
                )
                row = cursor.fetchone()
                if row is not None and row["edge_json"] != edge.to_json():
                    raise CatalogConflict("lineage digest exists with different edge content")
                if row is None:
                    cursor.execute(
                        "INSERT INTO ronin_lineage_edges("
                        "workspace_id,edge_digest,source_asset_id,source_version,"
                        "target_asset_id,target_version,edge_json,created_at) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            str(workspace_id),
                            edge.digest,
                            str(edge.source.asset_id),
                            str(edge.source.version),
                            str(edge.target.asset_id),
                            str(edge.target.version),
                            edge.to_json(),
                            str(current),
                        ),
                    )
            connection.commit()
            return edge
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def commit_multi_object_import(
        self,
        workspace_id: WorkspaceId,
        connections: tuple[ConnectionDefinition, ...],
        projects: tuple[ProjectManifest, ...],
        bindings: tuple[ProjectEnvironmentBindings, ...],
        *,
        now: Instant | str,
    ) -> MultiObjectBundleImportCommit:
        """Atomically apply project, connection and environment binding metadata."""

        connection_ids = [item.id for item in connections]
        project_ids = [item.project.id for item in projects]
        binding_keys = [(item.project_id, item.environment_id) for item in bindings]
        if len(connection_ids) != len(set(connection_ids)):
            raise ValueError("multi-object import connections must have unique ids")
        if len(project_ids) != len(set(project_ids)):
            raise ValueError("multi-object import projects must have unique ids")
        if len(binding_keys) != len(set(binding_keys)):
            raise ValueError("multi-object import bindings must be unique by project/environment")
        if any(item.project_id not in set(project_ids) for item in bindings):
            raise ValueError("multi-object import bindings must target staged projects")

        current = Instant(now)
        connection = self._connect()
        connections_created = projects_created = bindings_created = 0
        try:
            with connection.cursor() as cursor:
                self._require_active_workspace(cursor, workspace_id)
                for definition in sorted(connections, key=lambda item: str(item.id)):
                    payload = definition.to_json()
                    cursor.execute(
                        "SELECT definition_json FROM ronin_connections "
                        "WHERE workspace_id=%s AND connection_id=%s FOR UPDATE",
                        (str(workspace_id), str(definition.id)),
                    )
                    row = cursor.fetchone()
                    if row is not None and row["definition_json"] != payload:
                        raise MultiObjectBundleImportConflict(
                            f"connection id already exists with different content: {definition.id}"
                        )
                    if row is None:
                        cursor.execute(
                            "INSERT INTO ronin_connections("
                            "workspace_id,connection_id,definition_json,created_at,updated_at) "
                            "VALUES (%s,%s,%s,%s,%s)",
                            (str(workspace_id), str(definition.id), payload, str(current), str(current)),
                        )
                        connections_created += 1
                for manifest in sorted(projects, key=lambda item: str(item.project.id)):
                    project_id = manifest.project.id
                    payload = manifest.to_json()
                    cursor.execute(
                        "SELECT manifest_json FROM ronin_projects "
                        "WHERE workspace_id=%s AND project_id=%s FOR UPDATE",
                        (str(workspace_id), str(project_id)),
                    )
                    row = cursor.fetchone()
                    if row is not None and row["manifest_json"] != payload:
                        raise MultiObjectBundleImportConflict(
                            f"project id already exists with different content: {project_id}"
                        )
                    if row is None:
                        cursor.execute(
                            "INSERT INTO ronin_projects("
                            "workspace_id,project_id,manifest_json,created_at,updated_at) "
                            "VALUES (%s,%s,%s,%s,%s)",
                            (str(workspace_id), str(project_id), payload, str(current), str(current)),
                        )
                        projects_created += 1
                for item in sorted(bindings, key=lambda value: (str(value.project_id), str(value.environment_id))):
                    cursor.execute(
                        "SELECT definition_json FROM ronin_environments "
                        "WHERE workspace_id=%s AND environment_id=%s",
                        (str(workspace_id), str(item.environment_id)),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise MultiObjectBundleImportConflict(
                            f"target environment does not exist: {item.environment_id}"
                        )
                    if EnvironmentDefinition.from_json(row["definition_json"]).disabled:
                        raise MultiObjectBundleImportConflict(
                            f"target environment is disabled: {item.environment_id}"
                        )
                    payload = item.to_json()
                    cursor.execute(
                        "SELECT bindings_json FROM ronin_project_environment_bindings "
                        "WHERE workspace_id=%s AND project_id=%s AND environment_id=%s FOR UPDATE",
                        (str(workspace_id), str(item.project_id), str(item.environment_id)),
                    )
                    row = cursor.fetchone()
                    if row is not None and row["bindings_json"] != payload:
                        raise MultiObjectBundleImportConflict(
                            "target environment already has different project bindings"
                        )
                    if row is None:
                        cursor.execute(
                            "INSERT INTO ronin_project_environment_bindings("
                            "workspace_id,project_id,environment_id,bindings_json,created_at,updated_at) "
                            "VALUES (%s,%s,%s,%s,%s,%s)",
                            (str(workspace_id), str(item.project_id), str(item.environment_id), payload, str(current), str(current)),
                        )
                        bindings_created += 1
            connection.commit()
            return MultiObjectBundleImportCommit(connections_created, projects_created, bindings_created)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def commit_catalog_import(
        self,
        workspace_id: WorkspaceId,
        assets: tuple[CatalogAsset, ...],
        revisions: tuple[AssetRevision, ...],
        lineage: tuple[LineageEdge, ...],
        *,
        now: Instant | str,
    ) -> CatalogBundleImportCommit:
        """Atomically apply a verified catalog Bundle subgraph."""

        current = Instant(now)
        connection = self._connect()
        assets_created = revisions_created = lineage_created = 0
        try:
            with connection.cursor() as cursor:
                self._require_active_workspace(cursor, workspace_id)
                for asset in assets:
                    payload = asset.to_json()
                    cursor.execute(
                        "SELECT definition_json FROM ronin_catalog_assets "
                        "WHERE workspace_id=%s AND asset_id=%s FOR UPDATE",
                        (str(workspace_id), str(asset.id)),
                    )
                    row = cursor.fetchone()
                    if row is not None and row["definition_json"] != payload:
                        raise CatalogBundleImportConflict(
                            f"catalog asset conflicts with existing id: {asset.id}"
                        )
                    if row is None:
                        cursor.execute(
                            "INSERT INTO ronin_catalog_assets("
                            "workspace_id,asset_id,definition_json,created_at,updated_at) "
                            "VALUES (%s,%s,%s,%s,%s)",
                            (str(workspace_id), str(asset.id), payload, str(current), str(current)),
                        )
                        assets_created += 1
                for revision in revisions:
                    cursor.execute(
                        "SELECT 1 FROM ronin_catalog_assets WHERE workspace_id=%s AND asset_id=%s",
                        (str(workspace_id), str(revision.ref.asset_id)),
                    )
                    if cursor.fetchone() is None:
                        raise CatalogBundleImportConflict(
                            f"catalog revision references missing asset: {revision.ref.asset_id}"
                        )
                    payload = revision.to_json()
                    cursor.execute(
                        "SELECT revision_json FROM ronin_catalog_revisions "
                        "WHERE workspace_id=%s AND asset_id=%s AND version=%s FOR UPDATE",
                        (str(workspace_id), str(revision.ref.asset_id), str(revision.ref.version)),
                    )
                    row = cursor.fetchone()
                    if row is not None and row["revision_json"] != payload:
                        raise CatalogBundleImportConflict("catalog revision conflicts with existing identity")
                    if row is None:
                        cursor.execute(
                            "INSERT INTO ronin_catalog_revisions("
                            "workspace_id,asset_id,version,revision_json,created_at) "
                            "VALUES (%s,%s,%s,%s,%s)",
                            (str(workspace_id), str(revision.ref.asset_id), str(revision.ref.version), payload, str(current)),
                        )
                        revisions_created += 1
                for edge in lineage:
                    for ref in (edge.source, edge.target):
                        cursor.execute(
                            "SELECT 1 FROM ronin_catalog_revisions "
                            "WHERE workspace_id=%s AND asset_id=%s AND version=%s",
                            (str(workspace_id), str(ref.asset_id), str(ref.version)),
                        )
                        if cursor.fetchone() is None:
                            raise CatalogBundleImportConflict(
                                f"lineage references missing revision: {ref.asset_id}@{ref.version}"
                            )
                    payload = edge.to_json()
                    cursor.execute(
                        "SELECT edge_json FROM ronin_lineage_edges "
                        "WHERE workspace_id=%s AND edge_digest=%s FOR UPDATE",
                        (str(workspace_id), edge.digest),
                    )
                    row = cursor.fetchone()
                    if row is not None and row["edge_json"] != payload:
                        raise CatalogBundleImportConflict("lineage digest conflicts with existing content")
                    if row is None:
                        cursor.execute(
                            "INSERT INTO ronin_lineage_edges("
                            "workspace_id,edge_digest,source_asset_id,source_version,"
                            "target_asset_id,target_version,edge_json,created_at) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                            (str(workspace_id), edge.digest, str(edge.source.asset_id), str(edge.source.version),
                             str(edge.target.asset_id), str(edge.target.version), payload, str(current)),
                        )
                        lineage_created += 1
            connection.commit()
            return CatalogBundleImportCommit(assets_created, revisions_created, lineage_created)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def upstream(self, workspace_id: WorkspaceId, ref: AssetRef) -> tuple[LineageEdge, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT edge_json FROM ronin_lineage_edges WHERE workspace_id=%s "
                    "AND target_asset_id=%s AND target_version=%s ORDER BY edge_digest",
                    (str(workspace_id), str(ref.asset_id), str(ref.version)),
                )
                return tuple(LineageEdge.from_json(row["edge_json"]) for row in cursor.fetchall())
        finally:
            connection.close()

    def downstream(self, workspace_id: WorkspaceId, ref: AssetRef) -> tuple[LineageEdge, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT edge_json FROM ronin_lineage_edges WHERE workspace_id=%s "
                    "AND source_asset_id=%s AND source_version=%s ORDER BY edge_digest",
                    (str(workspace_id), str(ref.asset_id), str(ref.version)),
                )
                return tuple(LineageEdge.from_json(row["edge_json"]) for row in cursor.fetchall())
        finally:
            connection.close()


__all__ = ("PostgresDependencyError", "PostgresMetadataStore")
