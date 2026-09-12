"""Durable workspace-scoped connection-definition persistence for Public v1."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from studio_core import ConnectionDefinition, ConnectionId, WorkspaceId
from studio_orchestrator import Instant

from .sqlite import open_database
from .workspaces import WorkspaceNotFound, migrate_workspaces

_CONNECTION_SCHEMA_VERSION = 1
_CONNECTION_MIGRATIONS = {1: "connection_001.sql"}


class ConnectionConflict(RuntimeError):
    """Raised when a connection mutation conflicts with durable state."""


class ConnectionNotFound(KeyError):
    """Raised when a connection definition does not exist."""


def _execute_script_in_transaction(connection: sqlite3.Connection, script: str) -> None:
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)


def migrate_connections(connection: sqlite3.Connection, *, now: Instant | str) -> None:
    """Apply connection-owned schema changes after the workspace schema exists."""

    now = Instant(now)
    migrate_workspaces(connection, now=now)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS connection_schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = connection.execute(
        "SELECT MAX(version) AS version FROM connection_schema_migrations"
    ).fetchone()
    current = 0 if row is None or row["version"] is None else int(row["version"])
    if current > _CONNECTION_SCHEMA_VERSION:
        raise RuntimeError(
            f"connection schema {current} is newer than supported {_CONNECTION_SCHEMA_VERSION}"
        )
    migrations_dir = Path(__file__).with_name("migrations")
    for version in range(current + 1, _CONNECTION_SCHEMA_VERSION + 1):
        script = migrations_dir.joinpath(_CONNECTION_MIGRATIONS[version]).read_text(encoding="utf-8")
        connection.execute("BEGIN IMMEDIATE")
        try:
            _execute_script_in_transaction(connection, script)
            connection.execute(
                "INSERT INTO connection_schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, now),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def connection_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT MAX(version) AS version FROM connection_schema_migrations"
    ).fetchone()
    return 0 if row is None or row["version"] is None else int(row["version"])


class SqliteConnectionStore:
    """SQLite reference adapter for workspace-scoped, secret-reference-only definitions."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        self._path = path
        connection = open_database(path)
        try:
            migrate_connections(connection, now=migration_now)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return open_database(self._path)

    def _require_active_workspace(
        self, connection: sqlite3.Connection, workspace_id: WorkspaceId
    ) -> None:
        row = connection.execute(
            "SELECT archived_at FROM workspaces WHERE workspace_id=?", (str(workspace_id),)
        ).fetchone()
        if row is None:
            raise WorkspaceNotFound(str(workspace_id))
        if row["archived_at"] is not None:
            raise ConnectionConflict("cannot mutate connections in an archived workspace")

    def create_connection(
        self,
        workspace_id: WorkspaceId,
        definition: ConnectionDefinition,
        *,
        now: Instant | str,
    ) -> ConnectionDefinition:
        now = Instant(now)
        definition_json = definition.to_json()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            existing = connection.execute(
                "SELECT definition_json FROM connections WHERE workspace_id=? AND connection_id=?",
                (str(workspace_id), str(definition.id)),
            ).fetchone()
            if existing is not None:
                if existing["definition_json"] == definition_json:
                    connection.execute("COMMIT")
                    return definition
                raise ConnectionConflict(f"connection id already exists: {definition.id}")
            connection.execute(
                "INSERT INTO connections(workspace_id,connection_id,definition_json,created_at,updated_at) "
                "VALUES (?,?,?,?,?)",
                (str(workspace_id), str(definition.id), definition_json, now, now),
            )
            connection.execute("COMMIT")
            return definition
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def replace_connection(
        self,
        workspace_id: WorkspaceId,
        definition: ConnectionDefinition,
        *,
        now: Instant | str,
    ) -> ConnectionDefinition:
        now = Instant(now)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            cursor = connection.execute(
                "UPDATE connections SET definition_json=?,updated_at=?,row_version=row_version+1 "
                "WHERE workspace_id=? AND connection_id=?",
                (definition.to_json(), now, str(workspace_id), str(definition.id)),
            )
            if cursor.rowcount != 1:
                raise ConnectionNotFound(f"{workspace_id}/{definition.id}")
            connection.execute("COMMIT")
            return definition
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_connection(
        self, workspace_id: WorkspaceId, connection_id: ConnectionId
    ) -> ConnectionDefinition | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT definition_json FROM connections WHERE workspace_id=? AND connection_id=?",
                (str(workspace_id), str(connection_id)),
            ).fetchone()
            return None if row is None else ConnectionDefinition.from_json(row["definition_json"])
        finally:
            connection.close()

    def list_connections(self, workspace_id: WorkspaceId) -> tuple[ConnectionDefinition, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT definition_json FROM connections WHERE workspace_id=? ORDER BY connection_id",
                (str(workspace_id),),
            ).fetchall()
            return tuple(ConnectionDefinition.from_json(row["definition_json"]) for row in rows)
        finally:
            connection.close()

    def delete_connection(self, workspace_id: WorkspaceId, connection_id: ConnectionId) -> bool:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            cursor = connection.execute(
                "DELETE FROM connections WHERE workspace_id=? AND connection_id=?",
                (str(workspace_id), str(connection_id)),
            )
            connection.execute("COMMIT")
            return cursor.rowcount == 1
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
