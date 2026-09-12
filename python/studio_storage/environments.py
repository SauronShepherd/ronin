"""Durable workspace environment and project binding persistence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from studio_core import ProjectId, WorkspaceId
from studio_core.environments import (
    EnvironmentDefinition,
    EnvironmentId,
    ProjectEnvironmentBindings,
)
from studio_orchestrator import Instant

from .sqlite import open_database
from .workspaces import WorkspaceNotFound, migrate_workspaces

_ENVIRONMENT_SCHEMA_VERSION = 1
_ENVIRONMENT_MIGRATIONS = {1: "environment_001.sql"}


class EnvironmentConflict(RuntimeError):
    """Raised when an environment/binding mutation conflicts with durable state."""


class EnvironmentNotFound(KeyError):
    """Raised when an environment does not exist."""


def _execute_script_in_transaction(connection: sqlite3.Connection, script: str) -> None:
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)


def migrate_environments(connection: sqlite3.Connection, *, now: Instant | str) -> None:
    now = Instant(now)
    migrate_workspaces(connection, now=now)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS environment_schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = connection.execute(
        "SELECT MAX(version) AS version FROM environment_schema_migrations"
    ).fetchone()
    current = 0 if row is None or row["version"] is None else int(row["version"])
    if current > _ENVIRONMENT_SCHEMA_VERSION:
        raise RuntimeError(
            f"environment schema {current} is newer than supported {_ENVIRONMENT_SCHEMA_VERSION}"
        )
    migrations_dir = Path(__file__).with_name("migrations")
    for version in range(current + 1, _ENVIRONMENT_SCHEMA_VERSION + 1):
        script = migrations_dir.joinpath(_ENVIRONMENT_MIGRATIONS[version]).read_text(encoding="utf-8")
        connection.execute("BEGIN IMMEDIATE")
        try:
            _execute_script_in_transaction(connection, script)
            connection.execute(
                "INSERT INTO environment_schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, now),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def environment_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT MAX(version) AS version FROM environment_schema_migrations"
    ).fetchone()
    return 0 if row is None or row["version"] is None else int(row["version"])


class SqliteEnvironmentStore:
    """SQLite adapter for environment definitions and project-local deployment bindings."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        self._path = path
        connection = open_database(path)
        try:
            migrate_environments(connection, now=migration_now)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return open_database(self._path)

    @staticmethod
    def _require_active_workspace(
        connection: sqlite3.Connection,
        workspace_id: WorkspaceId,
    ) -> None:
        row = connection.execute(
            "SELECT archived_at FROM workspaces WHERE workspace_id=?",
            (str(workspace_id),),
        ).fetchone()
        if row is None:
            raise WorkspaceNotFound(str(workspace_id))
        if row["archived_at"] is not None:
            raise EnvironmentConflict("cannot mutate environments in an archived workspace")

    def put_environment(
        self,
        workspace_id: WorkspaceId,
        environment: EnvironmentDefinition,
        *,
        now: Instant | str,
    ) -> EnvironmentDefinition:
        now = Instant(now)
        payload = environment.to_json()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            existing = connection.execute(
                "SELECT definition_json FROM environments "
                "WHERE workspace_id=? AND environment_id=?",
                (str(workspace_id), str(environment.id)),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO environments(workspace_id,environment_id,definition_json,"
                    "created_at,updated_at) VALUES (?,?,?,?,?)",
                    (str(workspace_id), str(environment.id), payload, now, now),
                )
            elif existing["definition_json"] != payload:
                connection.execute(
                    "UPDATE environments SET definition_json=?,updated_at=?,row_version=row_version+1 "
                    "WHERE workspace_id=? AND environment_id=?",
                    (payload, now, str(workspace_id), str(environment.id)),
                )
            connection.execute("COMMIT")
            return environment
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_environment(
        self,
        workspace_id: WorkspaceId,
        environment_id: EnvironmentId,
    ) -> EnvironmentDefinition | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT definition_json FROM environments "
                "WHERE workspace_id=? AND environment_id=?",
                (str(workspace_id), str(environment_id)),
            ).fetchone()
            return None if row is None else EnvironmentDefinition.from_json(row["definition_json"])
        finally:
            connection.close()

    def list_environments(self, workspace_id: WorkspaceId) -> tuple[EnvironmentDefinition, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT definition_json FROM environments "
                "WHERE workspace_id=? ORDER BY environment_id",
                (str(workspace_id),),
            ).fetchall()
            return tuple(EnvironmentDefinition.from_json(row["definition_json"]) for row in rows)
        finally:
            connection.close()

    def put_project_bindings(
        self,
        workspace_id: WorkspaceId,
        bindings: ProjectEnvironmentBindings,
        *,
        now: Instant | str,
    ) -> ProjectEnvironmentBindings:
        now = Instant(now)
        payload = bindings.to_json()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            project = connection.execute(
                "SELECT 1 FROM workspace_projects WHERE workspace_id=? AND project_id=?",
                (str(workspace_id), str(bindings.project_id)),
            ).fetchone()
            if project is None:
                raise KeyError(f"project not registered: {bindings.project_id}")
            environment = connection.execute(
                "SELECT definition_json FROM environments "
                "WHERE workspace_id=? AND environment_id=?",
                (str(workspace_id), str(bindings.environment_id)),
            ).fetchone()
            if environment is None:
                raise EnvironmentNotFound(str(bindings.environment_id))
            definition = EnvironmentDefinition.from_json(environment["definition_json"])
            if definition.disabled:
                raise EnvironmentConflict("cannot bind a project to a disabled environment")

            existing = connection.execute(
                "SELECT bindings_json FROM project_environment_bindings "
                "WHERE workspace_id=? AND project_id=? AND environment_id=?",
                (
                    str(workspace_id),
                    str(bindings.project_id),
                    str(bindings.environment_id),
                ),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO project_environment_bindings("
                    "workspace_id,project_id,environment_id,bindings_json,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        str(workspace_id),
                        str(bindings.project_id),
                        str(bindings.environment_id),
                        payload,
                        now,
                        now,
                    ),
                )
            elif existing["bindings_json"] != payload:
                connection.execute(
                    "UPDATE project_environment_bindings SET bindings_json=?,updated_at=?,"
                    "row_version=row_version+1 WHERE workspace_id=? AND project_id=? "
                    "AND environment_id=?",
                    (
                        payload,
                        now,
                        str(workspace_id),
                        str(bindings.project_id),
                        str(bindings.environment_id),
                    ),
                )
            connection.execute("COMMIT")
            return bindings
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
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
            row = connection.execute(
                "SELECT bindings_json FROM project_environment_bindings "
                "WHERE workspace_id=? AND project_id=? AND environment_id=?",
                (str(workspace_id), str(project_id), str(environment_id)),
            ).fetchone()
            return None if row is None else ProjectEnvironmentBindings.from_json(row["bindings_json"])
        finally:
            connection.close()


__all__ = (
    "EnvironmentConflict",
    "EnvironmentNotFound",
    "SqliteEnvironmentStore",
    "environment_schema_version",
    "migrate_environments",
)
