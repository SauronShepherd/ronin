"""Append-only PostgreSQL audit persistence for shared Ronin server profiles."""

from __future__ import annotations

from typing import Any

from studio_core import WorkspaceId
from studio_core.audit import AuditEvent, AuditEventId

from .audit import AuditConflict
from .postgres_core import _psycopg
from .workspaces import WorkspaceNotFound

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ronin_audit_events (
    workspace_id TEXT NOT NULL REFERENCES ronin_workspaces(workspace_id) ON DELETE CASCADE,
    audit_event_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    actor_kind TEXT NOT NULL CHECK (actor_kind IN ('user','service','local','token')),
    actor_ref TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_kind TEXT NOT NULL,
    resource_ref TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('succeeded','failed','allowed','denied')),
    request_id TEXT,
    digest TEXT NOT NULL,
    event_json TEXT NOT NULL,
    PRIMARY KEY(workspace_id, audit_event_id)
);
CREATE INDEX IF NOT EXISTS ronin_audit_resource_idx
    ON ronin_audit_events(
        workspace_id, resource_kind, resource_ref, occurred_at DESC, audit_event_id DESC
    );
"""


class PostgresAuditStore:
    """Append-only PostgreSQL adapter; no update/delete operations are exposed."""

    def __init__(self, dsn: str, *, application_name: str = "ronin-audit") -> None:
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
                cursor.execute("SELECT to_regclass('ronin_workspaces') AS table_name")
                row = cursor.fetchone()
                if row is None or row["table_name"] is None:
                    raise RuntimeError(
                        "PostgreSQL audit store requires migrated ronin_workspaces metadata"
                    )
                cursor.execute(_SCHEMA)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def append(self, workspace_id: WorkspaceId, event: AuditEvent) -> AuditEvent:
        payload = event.to_json()
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM ronin_workspaces WHERE workspace_id=%s",
                    (workspace_id.value,),
                )
                if cursor.fetchone() is None:
                    raise WorkspaceNotFound(workspace_id.value)
                cursor.execute(
                    "SELECT event_json FROM ronin_audit_events "
                    "WHERE workspace_id=%s AND audit_event_id=%s FOR UPDATE",
                    (workspace_id.value, event.id.value),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    if existing["event_json"] == payload:
                        connection.commit()
                        return event
                    raise AuditConflict(f"audit event id already exists: {event.id}")
                cursor.execute(
                    "INSERT INTO ronin_audit_events("
                    "workspace_id,audit_event_id,occurred_at,actor_kind,actor_ref,action,"
                    "resource_kind,resource_ref,outcome,request_id,digest,event_json) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        workspace_id.value,
                        event.id.value,
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
            connection.commit()
            return event
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get(self, workspace_id: WorkspaceId, event_id: AuditEventId) -> AuditEvent | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT event_json FROM ronin_audit_events "
                    "WHERE workspace_id=%s AND audit_event_id=%s",
                    (workspace_id.value, event_id.value),
                )
                row = cursor.fetchone()
            return None if row is None else AuditEvent.from_json(str(row["event_json"]))
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
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT event_json FROM ronin_audit_events "
                    "WHERE workspace_id=%s AND resource_kind=%s AND resource_ref=%s "
                    "ORDER BY occurred_at DESC,audit_event_id DESC LIMIT %s",
                    (workspace_id.value, resource_kind, resource_ref, limit),
                )
                rows = cursor.fetchall()
            return tuple(AuditEvent.from_json(str(row["event_json"])) for row in rows)
        finally:
            connection.close()


__all__ = ("PostgresAuditStore",)
