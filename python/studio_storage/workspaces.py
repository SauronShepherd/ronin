"""Durable workspace and project-registration persistence for Public v1."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from studio_core import ProjectId, ProjectManifest, Workspace, WorkspaceId
from studio_orchestrator import Instant

from .sqlite import open_database

_WORKSPACE_SCHEMA_VERSION = 1
_WORKSPACE_MIGRATIONS = {1: "workspace_001.sql"}


class WorkspaceConflict(RuntimeError):
    """Raised when a workspace mutation conflicts with durable state."""


class WorkspaceNotFound(KeyError):
    """Raised when a workspace does not exist."""


class ProjectRegistrationConflict(RuntimeError):
    """Raised when a project registration conflicts with existing workspace state."""


def _execute_script_in_transaction(connection: sqlite3.Connection, script: str) -> None:
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)


def migrate_workspaces(connection: sqlite3.Connection, *, now: Instant | str) -> None:
    """Apply workspace-owned schema changes without changing the v0.1 lifecycle schema ledger."""

    now = Instant(now)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS workspace_schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = connection.execute(
        "SELECT MAX(version) AS version FROM workspace_schema_migrations"
    ).fetchone()
    current = 0 if row is None or row["version"] is None else int(row["version"])
    if current > _WORKSPACE_SCHEMA_VERSION:
        raise RuntimeError(
            f"workspace schema {current} is newer than supported {_WORKSPACE_SCHEMA_VERSION}"
        )
    migrations_dir = Path(__file__).with_name("migrations")
    for version in range(current + 1, _WORKSPACE_SCHEMA_VERSION + 1):
        script = migrations_dir.joinpath(_WORKSPACE_MIGRATIONS[version]).read_text(encoding="utf-8")
        connection.execute("BEGIN IMMEDIATE")
        try:
            _execute_script_in_transaction(connection, script)
            connection.execute(
                "INSERT INTO workspace_schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, now),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def workspace_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT MAX(version) AS version FROM workspace_schema_migrations"
    ).fetchone()
    return 0 if row is None or row["version"] is None else int(row["version"])


def _workspace(row: sqlite3.Row) -> Workspace:
    return Workspace(
        id=WorkspaceId(row["workspace_id"]),
        name=row["name"],
        description=row["description"],
        state="archived" if row["archived_at"] is not None else "active",
    )


class SqliteWorkspaceStore:
    """SQLite reference adapter for workspaces and portable project registrations."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        self._path = path
        connection = open_database(path)
        try:
            migrate_workspaces(connection, now=migration_now)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return open_database(self._path)

    def create_workspace(self, workspace: Workspace, *, now: Instant | str) -> Workspace:
        if workspace.archived:
            raise ValueError("new workspace must be active")
        now = Instant(now)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM workspaces WHERE workspace_id=?", (str(workspace.id),)
            ).fetchone()
            if existing is not None:
                found = _workspace(existing)
                if found == workspace:
                    connection.execute("COMMIT")
                    return found
                raise WorkspaceConflict(f"workspace id already exists: {workspace.id}")
            connection.execute(
                "INSERT INTO workspaces(workspace_id,name,description,archived_at,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (str(workspace.id), workspace.name, workspace.description, None, now, now),
            )
            connection.execute("COMMIT")
            return workspace
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_workspace(self, workspace_id: WorkspaceId) -> Workspace | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM workspaces WHERE workspace_id=?", (str(workspace_id),)
            ).fetchone()
            return None if row is None else _workspace(row)
        finally:
            connection.close()

    def list_workspaces(self) -> tuple[Workspace, ...]:
        connection = self._connect()
        try:
            rows = connection.execute("SELECT * FROM workspaces ORDER BY workspace_id").fetchall()
            return tuple(_workspace(row) for row in rows)
        finally:
            connection.close()

    def update_workspace(self, workspace: Workspace, *, now: Instant | str) -> Workspace:
        now = Instant(now)
        connection = self._connect()
        try:
            archived_at: str | None = str(now) if workspace.archived else None
            cursor = connection.execute(
                "UPDATE workspaces SET name=?,description=?,archived_at=?,updated_at=?,"
                "row_version=row_version+1 WHERE workspace_id=?",
                (
                    workspace.name,
                    workspace.description,
                    archived_at,
                    now,
                    str(workspace.id),
                ),
            )
            if cursor.rowcount != 1:
                raise WorkspaceNotFound(str(workspace.id))
            return workspace
        finally:
            connection.close()

    def register_project(
        self,
        workspace_id: WorkspaceId,
        manifest: ProjectManifest,
        *,
        now: Instant | str,
    ) -> ProjectManifest:
        now = Instant(now)
        project_id = manifest.project.id
        manifest_json = manifest.to_json()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            workspace_row = connection.execute(
                "SELECT archived_at FROM workspaces WHERE workspace_id=?", (str(workspace_id),)
            ).fetchone()
            if workspace_row is None:
                raise WorkspaceNotFound(str(workspace_id))
            if workspace_row["archived_at"] is not None:
                raise WorkspaceConflict("cannot register a project in an archived workspace")
            existing = connection.execute(
                "SELECT manifest_json FROM workspace_projects WHERE workspace_id=? AND project_id=?",
                (str(workspace_id), str(project_id)),
            ).fetchone()
            if existing is not None:
                if existing["manifest_json"] == manifest_json:
                    connection.execute("COMMIT")
                    return manifest
                raise ProjectRegistrationConflict(
                    f"project registration already exists with different intent: {project_id}"
                )
            connection.execute(
                "INSERT INTO workspace_projects(workspace_id,project_id,manifest_json,created_at,updated_at) "
                "VALUES (?,?,?,?,?)",
                (str(workspace_id), str(project_id), manifest_json, now, now),
            )
            connection.execute("COMMIT")
            return manifest
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def replace_project(
        self,
        workspace_id: WorkspaceId,
        manifest: ProjectManifest,
        *,
        now: Instant | str,
    ) -> ProjectManifest:
        now = Instant(now)
        project_id = manifest.project.id
        connection = self._connect()
        try:
            cursor = connection.execute(
                "UPDATE workspace_projects SET manifest_json=?,updated_at=?,row_version=row_version+1 "
                "WHERE workspace_id=? AND project_id=?",
                (manifest.to_json(), now, str(workspace_id), str(project_id)),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"{workspace_id}/{project_id}")
            return manifest
        finally:
            connection.close()

    def get_project(
        self, workspace_id: WorkspaceId, project_id: ProjectId
    ) -> ProjectManifest | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT manifest_json FROM workspace_projects WHERE workspace_id=? AND project_id=?",
                (str(workspace_id), str(project_id)),
            ).fetchone()
            return None if row is None else ProjectManifest.from_json(row["manifest_json"])
        finally:
            connection.close()

    def list_projects(self, workspace_id: WorkspaceId) -> tuple[ProjectManifest, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT manifest_json FROM workspace_projects WHERE workspace_id=? ORDER BY project_id",
                (str(workspace_id),),
            ).fetchall()
            return tuple(ProjectManifest.from_json(row["manifest_json"]) for row in rows)
        finally:
            connection.close()

    def unregister_project(self, workspace_id: WorkspaceId, project_id: ProjectId) -> bool:
        connection = self._connect()
        try:
            cursor = connection.execute(
                "DELETE FROM workspace_projects WHERE workspace_id=? AND project_id=?",
                (str(workspace_id), str(project_id)),
            )
            return cursor.rowcount == 1
        finally:
            connection.close()
