"""Atomic SQLite commit boundary for supported multi-object Ronin Bundle imports."""

from __future__ import annotations

from pathlib import Path

from studio_core import ConnectionDefinition, ProjectManifest, WorkspaceId
from studio_core.environments import EnvironmentDefinition, ProjectEnvironmentBindings
from studio_orchestrator import Instant

from .bundle_multi_import_port import (
    MultiObjectBundleImportCommit,
    MultiObjectBundleImportConflict,
)
from .connections import SqliteConnectionStore, migrate_connections
from .environments import migrate_environments
from .sqlite import open_database
from .workspaces import SqliteWorkspaceStore, migrate_workspaces


class SqliteMultiObjectBundleImportStore(SqliteWorkspaceStore, SqliteConnectionStore):
    """SQLite metadata adapter with one transaction for supported Bundle objects."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        SqliteWorkspaceStore.__init__(self, path, migration_now=migration_now)
        connection = open_database(path)
        try:
            migrate_workspaces(connection, now=migration_now)
            migrate_connections(connection, now=migration_now)
            migrate_environments(connection, now=migration_now)
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
        """Create/exact-noop all supported objects in one metadata transaction."""

        connection_ids = [item.id for item in connections]
        project_ids = [item.project.id for item in projects]
        binding_keys = [(item.project_id, item.environment_id) for item in bindings]
        if len(connection_ids) != len(set(connection_ids)):
            raise ValueError("multi-object import connections must have unique ids")
        if len(project_ids) != len(set(project_ids)):
            raise ValueError("multi-object import projects must have unique ids")
        if len(binding_keys) != len(set(binding_keys)):
            raise ValueError("multi-object import bindings must be unique by project/environment")
        project_id_set = set(project_ids)
        if any(item.project_id not in project_id_set for item in bindings):
            raise ValueError("multi-object import bindings must target staged projects")

        current = Instant(now)
        database = self._connect()
        try:
            database.execute("BEGIN IMMEDIATE")
            workspace = database.execute(
                "SELECT archived_at FROM workspaces WHERE workspace_id=?",
                (str(workspace_id),),
            ).fetchone()
            if workspace is None:
                raise MultiObjectBundleImportConflict("target workspace does not exist")
            if workspace["archived_at"] is not None:
                raise MultiObjectBundleImportConflict("target workspace is archived")

            connections_created = 0
            for definition in sorted(connections, key=lambda item: str(item.id)):
                definition_json = definition.to_json()
                existing = database.execute(
                    "SELECT definition_json FROM connections "
                    "WHERE workspace_id=? AND connection_id=?",
                    (str(workspace_id), str(definition.id)),
                ).fetchone()
                if existing is None:
                    database.execute(
                        "INSERT INTO connections("
                        "workspace_id,connection_id,definition_json,created_at,updated_at) "
                        "VALUES (?,?,?,?,?)",
                        (
                            str(workspace_id),
                            str(definition.id),
                            definition_json,
                            current,
                            current,
                        ),
                    )
                    connections_created += 1
                elif existing["definition_json"] != definition_json:
                    raise MultiObjectBundleImportConflict(
                        f"connection id already exists with different content: {definition.id}"
                    )

            projects_created = 0
            for manifest in sorted(projects, key=lambda item: str(item.project.id)):
                manifest_json = manifest.to_json()
                project_id = manifest.project.id
                existing = database.execute(
                    "SELECT manifest_json FROM workspace_projects "
                    "WHERE workspace_id=? AND project_id=?",
                    (str(workspace_id), str(project_id)),
                ).fetchone()
                if existing is None:
                    database.execute(
                        "INSERT INTO workspace_projects("
                        "workspace_id,project_id,manifest_json,created_at,updated_at) "
                        "VALUES (?,?,?,?,?)",
                        (
                            str(workspace_id),
                            str(project_id),
                            manifest_json,
                            current,
                            current,
                        ),
                    )
                    projects_created += 1
                elif existing["manifest_json"] != manifest_json:
                    raise MultiObjectBundleImportConflict(
                        f"project id already exists with different content: {project_id}"
                    )

            bindings_created = 0
            for item in sorted(
                bindings,
                key=lambda value: (str(value.project_id), str(value.environment_id)),
            ):
                environment = database.execute(
                    "SELECT definition_json FROM environments "
                    "WHERE workspace_id=? AND environment_id=?",
                    (str(workspace_id), str(item.environment_id)),
                ).fetchone()
                if environment is None:
                    raise MultiObjectBundleImportConflict(
                        f"target environment does not exist: {item.environment_id}"
                    )
                definition = EnvironmentDefinition.from_json(environment["definition_json"])
                if definition.disabled:
                    raise MultiObjectBundleImportConflict(
                        f"target environment is disabled: {item.environment_id}"
                    )

                bindings_json = item.to_json()
                existing = database.execute(
                    "SELECT bindings_json FROM project_environment_bindings "
                    "WHERE workspace_id=? AND project_id=? AND environment_id=?",
                    (
                        str(workspace_id),
                        str(item.project_id),
                        str(item.environment_id),
                    ),
                ).fetchone()
                if existing is None:
                    database.execute(
                        "INSERT INTO project_environment_bindings("
                        "workspace_id,project_id,environment_id,bindings_json,"
                        "created_at,updated_at) VALUES (?,?,?,?,?,?)",
                        (
                            str(workspace_id),
                            str(item.project_id),
                            str(item.environment_id),
                            bindings_json,
                            current,
                            current,
                        ),
                    )
                    bindings_created += 1
                elif existing["bindings_json"] != bindings_json:
                    raise MultiObjectBundleImportConflict(
                        "target environment already has different project bindings"
                    )

            database.execute("COMMIT")
            return MultiObjectBundleImportCommit(
                connections_created,
                projects_created,
                bindings_created,
            )
        except Exception:
            if database.in_transaction:
                database.execute("ROLLBACK")
            raise
        finally:
            database.close()


__all__ = ("SqliteMultiObjectBundleImportStore",)
