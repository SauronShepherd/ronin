"""Atomic SQLite commit boundary for native project Bundle imports."""

from __future__ import annotations

from pathlib import Path

from studio_core import ProjectManifest, WorkspaceId
from studio_core.environments import EnvironmentDefinition, ProjectEnvironmentBindings
from studio_orchestrator import Instant

from .bundle_import_port import ProjectBundleImportCommit
from .environments import migrate_environments
from .sqlite import open_database
from .workspaces import SqliteWorkspaceStore, migrate_workspaces


class ProjectBundleImportConflict(RuntimeError):
    """Raised when target state changed or conflicts with a planned native import."""


class SqliteProjectBundleImportStore(SqliteWorkspaceStore):
    """Workspace store with one-transaction project plus environment-binding import."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        super().__init__(path, migration_now=migration_now)
        connection = open_database(path)
        try:
            migrate_workspaces(connection, now=migration_now)
            migrate_environments(connection, now=migration_now)
        finally:
            connection.close()

    def commit_project_import(
        self,
        workspace_id: WorkspaceId,
        project: ProjectManifest,
        bindings: ProjectEnvironmentBindings | None,
        *,
        now: Instant | str,
    ) -> ProjectBundleImportCommit:
        """Atomically create/no-op a project and its explicit deployment bindings."""

        current = Instant(now)
        project_id = project.project.id
        if bindings is not None and bindings.project_id != project_id:
            raise ValueError("import bindings must target the imported project")

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            workspace = connection.execute(
                "SELECT archived_at FROM workspaces WHERE workspace_id=?",
                (str(workspace_id),),
            ).fetchone()
            if workspace is None:
                raise ProjectBundleImportConflict("target workspace does not exist")
            if workspace["archived_at"] is not None:
                raise ProjectBundleImportConflict("target workspace is archived")

            project_json = project.to_json()
            existing_project = connection.execute(
                "SELECT manifest_json FROM workspace_projects "
                "WHERE workspace_id=? AND project_id=?",
                (str(workspace_id), str(project_id)),
            ).fetchone()
            project_created = False
            if existing_project is None:
                connection.execute(
                    "INSERT INTO workspace_projects("
                    "workspace_id,project_id,manifest_json,created_at,updated_at) "
                    "VALUES (?,?,?,?,?)",
                    (str(workspace_id), str(project_id), project_json, current, current),
                )
                project_created = True
            elif existing_project["manifest_json"] != project_json:
                raise ProjectBundleImportConflict(
                    "project id already exists with different portable content"
                )

            bindings_created = False
            if bindings is not None:
                environment = connection.execute(
                    "SELECT definition_json FROM environments "
                    "WHERE workspace_id=? AND environment_id=?",
                    (str(workspace_id), str(bindings.environment_id)),
                ).fetchone()
                if environment is None:
                    raise ProjectBundleImportConflict("target environment does not exist")
                definition = EnvironmentDefinition.from_json(environment["definition_json"])
                if definition.disabled:
                    raise ProjectBundleImportConflict("target environment is disabled")

                bindings_json = bindings.to_json()
                existing_bindings = connection.execute(
                    "SELECT bindings_json FROM project_environment_bindings "
                    "WHERE workspace_id=? AND project_id=? AND environment_id=?",
                    (
                        str(workspace_id),
                        str(project_id),
                        str(bindings.environment_id),
                    ),
                ).fetchone()
                if existing_bindings is None:
                    connection.execute(
                        "INSERT INTO project_environment_bindings("
                        "workspace_id,project_id,environment_id,bindings_json,"
                        "created_at,updated_at) VALUES (?,?,?,?,?,?)",
                        (
                            str(workspace_id),
                            str(project_id),
                            str(bindings.environment_id),
                            bindings_json,
                            current,
                            current,
                        ),
                    )
                    bindings_created = True
                elif existing_bindings["bindings_json"] != bindings_json:
                    raise ProjectBundleImportConflict(
                        "target environment already has different project bindings"
                    )

            connection.execute("COMMIT")
            return ProjectBundleImportCommit(project_created, bindings_created)
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()


__all__ = ("ProjectBundleImportConflict", "SqliteProjectBundleImportStore")
