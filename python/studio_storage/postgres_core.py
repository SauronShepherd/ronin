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
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

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
                    "INSERT INTO ronin_workspaces(workspace_id,name,description,archived_at,created_at,updated_at) "
                    "VALUES (%s,%s,%s,NULL,%s,%s)",
                    (str(workspace.id), workspace.name, workspace.description, str(current), str(current)),
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
                    "UPDATE ronin_workspaces SET name=%s,description=%s,archived_at=%s,updated_at=%s,"
                    "row_version=row_version+1 WHERE workspace_id=%s",
                    (workspace.name, workspace.description, archived_at, str(current), str(workspace.id)),
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
                    "SELECT manifest_json FROM ronin_projects WHERE workspace_id=%s AND project_id=%s FOR UPDATE",
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
                    "INSERT INTO ronin_projects(workspace_id,project_id,manifest_json,created_at,updated_at) "
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
                    "UPDATE ronin_projects SET manifest_json=%s,updated_at=%s,row_version=row_version+1 "
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
                    "SELECT manifest_json FROM ronin_projects WHERE workspace_id=%s AND project_id=%s",
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
                    "SELECT manifest_json FROM ronin_projects WHERE workspace_id=%s ORDER BY project_id",
                    (str(workspace_id),),
                )
                return tuple(ProjectManifest.from_json(row["manifest_json"]) for row in cursor.fetchall())
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
                deleted = cursor.rowcount == 1
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
                    "INSERT INTO ronin_environments(workspace_id,environment_id,definition_json,created_at,updated_at) "
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
                    "SELECT definition_json FROM ronin_environments WHERE workspace_id=%s AND environment_id=%s",
                    (str(workspace_id), str(environment_id)),
                )
                row = cursor.fetchone()
                return None if row is None else EnvironmentDefinition.from_json(row["definition_json"])
        finally:
            connection.close()

    def list_environments(self, workspace_id: WorkspaceId) -> tuple[EnvironmentDefinition, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT definition_json FROM ronin_environments WHERE workspace_id=%s ORDER BY environment_id",
                    (str(workspace_id),),
                )
                return tuple(EnvironmentDefinition.from_json(row["definition_json"]) for row in cursor.fetchall())
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
                    "SELECT definition_json FROM ronin_environments WHERE workspace_id=%s AND environment_id=%s",
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
                        str(workspace_id), str(bindings.project_id), str(bindings.environment_id),
                        bindings.to_json(), str(current), str(current),
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
                return None if row is None else ProjectEnvironmentBindings.from_json(row["bindings_json"])
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
                    "SELECT definition_json FROM ronin_connections WHERE workspace_id=%s AND connection_id=%s FOR UPDATE",
                    (str(workspace_id), str(definition.id)),
                )
                row = cursor.fetchone()
                if row is not None:
                    if row["definition_json"] == payload:
                        connection.commit()
                        return definition
                    raise ConnectionConflict(f"connection id already exists: {definition.id}")
                cursor.execute(
                    "INSERT INTO ronin_connections(workspace_id,connection_id,definition_json,created_at,updated_at) "
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
                    "UPDATE ronin_connections SET definition_json=%s,updated_at=%s,row_version=row_version+1 "
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
                    "SELECT definition_json FROM ronin_connections WHERE workspace_id=%s AND connection_id=%s",
                    (str(workspace_id), str(connection_id)),
                )
                row = cursor.fetchone()
                return None if row is None else ConnectionDefinition.from_json(row["definition_json"])
        finally:
            connection.close()

    def list_connections(self, workspace_id: WorkspaceId) -> tuple[ConnectionDefinition, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT definition_json FROM ronin_connections WHERE workspace_id=%s ORDER BY connection_id",
                    (str(workspace_id),),
                )
                return tuple(ConnectionDefinition.from_json(row["definition_json"]) for row in cursor.fetchall())
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
                deleted = cursor.rowcount == 1
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
                    "SELECT definition_json FROM ronin_catalog_assets WHERE workspace_id=%s AND asset_id=%s FOR UPDATE",
                    (str(workspace_id), str(asset.id)),
                )
                row = cursor.fetchone()
                if row is not None:
                    if row["definition_json"] == payload:
                        connection.commit()
                        return asset
                    raise CatalogConflict(f"catalog asset id already exists: {asset.id}")
                cursor.execute(
                    "INSERT INTO ronin_catalog_assets(workspace_id,asset_id,definition_json,created_at,updated_at) "
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
                    "UPDATE ronin_catalog_assets SET definition_json=%s,updated_at=%s,row_version=row_version+1 "
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
                    "SELECT definition_json FROM ronin_catalog_assets WHERE workspace_id=%s AND asset_id=%s",
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
                    "SELECT definition_json FROM ronin_catalog_assets WHERE workspace_id=%s ORDER BY asset_id",
                    (str(workspace_id),),
                )
                return tuple(CatalogAsset.from_json(row["definition_json"]) for row in cursor.fetchall())
        finally:
            connection.close()

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
                    "SELECT revision_json FROM ronin_catalog_revisions WHERE workspace_id=%s AND asset_id=%s AND version=%s FOR UPDATE",
                    (str(workspace_id), str(revision.ref.asset_id), str(revision.ref.version)),
                )
                row = cursor.fetchone()
                if row is not None and row["revision_json"] != payload:
                    raise CatalogConflict("asset revision identity already exists with different metadata")
                if row is None:
                    cursor.execute(
                        "INSERT INTO ronin_catalog_revisions(workspace_id,asset_id,version,revision_json,created_at) "
                        "VALUES (%s,%s,%s,%s,%s)",
                        (
                            str(workspace_id), str(revision.ref.asset_id), str(revision.ref.version),
                            payload, str(current),
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
                    "SELECT revision_json FROM ronin_catalog_revisions WHERE workspace_id=%s AND asset_id=%s AND version=%s",
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
                        "SELECT 1 FROM ronin_catalog_revisions WHERE workspace_id=%s AND asset_id=%s AND version=%s",
                        (str(workspace_id), str(ref.asset_id), str(ref.version)),
                    )
                    if cursor.fetchone() is None:
                        raise CatalogAssetNotFound(f"{ref.asset_id}@{ref.version}")
                cursor.execute(
                    "SELECT edge_json FROM ronin_lineage_edges WHERE workspace_id=%s AND edge_digest=%s FOR UPDATE",
                    (str(workspace_id), edge.digest),
                )
                row = cursor.fetchone()
                if row is not None and row["edge_json"] != edge.to_json():
                    raise CatalogConflict("lineage digest exists with different edge content")
                if row is None:
                    cursor.execute(
                        "INSERT INTO ronin_lineage_edges("
                        "workspace_id,edge_digest,source_asset_id,source_version,target_asset_id,target_version,edge_json,created_at) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            str(workspace_id), edge.digest, str(edge.source.asset_id),
                            str(edge.source.version), str(edge.target.asset_id),
                            str(edge.target.version), edge.to_json(), str(current),
                        ),
                    )
            connection.commit()
            return edge
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
