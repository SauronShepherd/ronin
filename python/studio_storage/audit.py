"""Append-only audit persistence for Ronin Public v1."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from studio_core import WorkspaceId
from studio_core.audit import AuditEvent, AuditEventId
from studio_orchestrator import Instant

from .sqlite import open_database
from .workspaces import WorkspaceNotFound, migrate_workspaces

_AUDIT_SCHEMA_VERSION = 1
_AUDIT_MIGRATIONS = {1: "audit_001.sql"}


class AuditConflict(RuntimeError):
    """Raised when an audit event ID is reused with different content."""


def _execute_script_in_transaction(connection: sqlite3.Connection, script: str) -> None:
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)


def migrate_audit(connection: sqlite3.Connection, *, now: Instant | str) -> None:
    now = Instant(now)
    migrate_workspaces(connection, now=now)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS audit_schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = connection.execute(
        "SELECT MAX(version) AS version FROM audit_schema_migrations"
    ).fetchone()
    current = 0 if row is None or row["version"] is None else int(row["version"])
    if current > _AUDIT_SCHEMA_VERSION:
        raise RuntimeError(f"audit schema {current} is newer than supported {_AUDIT_SCHEMA_VERSION}")
    migrations_dir = Path(__file__).with_name("migrations")
    for version in range(current + 1, _AUDIT_SCHEMA_VERSION + 1):
        script = migrations_dir.joinpath(_AUDIT_MIGRATIONS[version]).read_text(encoding="utf-8")
        connection.execute("BEGIN IMMEDIATE")
        try:
            _execute_script_in_transaction(connection, script)
            connection.execute(
                "INSERT INTO audit_schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, now),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def audit_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT MAX(version) AS version FROM audit_schema_migrations").fetchone()
    return 0 if row is None or row["version"] is None else int(row["version"])


class SqliteAuditStore:
    """Append-only SQLite audit store; no update/delete methods are exposed."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        self._path = path
        connection = open_database(path)
        try:
            migrate_audit(connection, now=migration_now)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return open_database(self._path)

    def append(self, workspace_id: WorkspaceId, event: AuditEvent) -> AuditEvent:
        payload = event.to_json()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            workspace = connection.execute(
                "SELECT 1 FROM workspaces WHERE workspace_id=?", (str(workspace_id),)
            ).fetchone()
            if workspace is None:
                raise WorkspaceNotFound(str(workspace_id))
            existing = connection.execute(
                "SELECT event_json FROM audit_events WHERE workspace_id=? AND audit_event_id=?",
                (str(workspace_id), str(event.id)),
            ).fetchone()
            if existing is not None:
                if existing["event_json"] == payload:
                    connection.execute("COMMIT")
                    return event
                raise AuditConflict(f"audit event id already exists: {event.id}")
            connection.execute(
                "INSERT INTO audit_events(workspace_id,audit_event_id,occurred_at,actor_kind,actor_ref,"
                "action,resource_kind,resource_ref,outcome,request_id,digest,event_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(workspace_id),
                    str(event.id),
                    event.occurred_at,
                    event.actor.kind,
                    event.actor.ref,
                    event.action,
                    event.resource.kind,
                    event.resource.ref,
                    event.outcome,
                    event.request_id,
                    event.digest,
                    payload,
                ),
            )
            connection.execute("COMMIT")
            return event
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get(self, workspace_id: WorkspaceId, event_id: AuditEventId) -> AuditEvent | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT event_json FROM audit_events WHERE workspace_id=? AND audit_event_id=?",
                (str(workspace_id), str(event_id)),
            ).fetchone()
            return None if row is None else AuditEvent.from_json(row["event_json"])
        finally:
            connection.close()

    def list_for_resource(
        self,
        workspace_id: WorkspaceId,
        *,
        resource_kind: str,
        resource_ref: str,
        limit: int = 100,
    ) -> tuple[AuditEvent, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("audit list limit must be between 1 and 1000")
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT event_json FROM audit_events WHERE workspace_id=? AND resource_kind=? "
                "AND resource_ref=? ORDER BY occurred_at DESC,audit_event_id DESC LIMIT ?",
                (str(workspace_id), resource_kind, resource_ref, limit),
            ).fetchall()
            return tuple(AuditEvent.from_json(row["event_json"]) for row in rows)
        finally:
            connection.close()
