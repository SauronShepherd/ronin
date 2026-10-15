from __future__ import annotations

from types import SimpleNamespace

import pytest
from studio_core import WorkspaceId
from studio_core.audit import AuditActor, AuditEvent, AuditEventId, AuditResource
from studio_orchestrator import Instant
from studio_storage.postgres_audit import PostgresAuditStore


class _Cursor:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows
        self.executed: list[tuple[object, object]] = []

    def execute(self, query: object, params: object = ()) -> None:
        self.executed.append((query, params))

    def fetchone(self) -> object:
        return self.rows.pop(0) if self.rows else None

    def fetchall(self) -> list[object]:
        return self.rows

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _Connection:
    def __init__(self, rows: list[object]) -> None:
        self.cursor_instance = _Cursor(rows)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self) -> _Cursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def _event(event_id: str = "audit-1") -> AuditEvent:
    return AuditEvent(
        AuditEventId(event_id),
        Instant("2026-09-14T04:00:00.000000Z"),
        AuditActor("user", "principal-1"),
        "authorize:job.read",
        AuditResource("workspace_resource", "workspace/project:project-1"),
        "allowed",
        "request-1",
        (("decision_reason", "role_permission_allowed"),),
    )


def test_constructor_and_migrate(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _Connection([{"table_name": "ronin_workspaces"}])
    monkeypatch.setattr(
        "studio_storage.postgres_audit._psycopg",
        lambda: (
            SimpleNamespace(connect=lambda *_args, **_kwargs: connection),
            object(),
        ),
    )
    store = PostgresAuditStore("postgresql://ronin")
    assert store._application_name == "ronin-audit"
    assert connection.commits == 1
    assert connection.closed


def test_validation_and_missing_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="DSN"):
        PostgresAuditStore.__new__(PostgresAuditStore).__init__(" ")
    connection = _Connection([{"table_name": None}])
    store = PostgresAuditStore.__new__(PostgresAuditStore)
    monkeypatch.setattr(store, "_connect", lambda: connection)
    with pytest.raises(RuntimeError, match="requires migrated"):
        store.migrate()
    assert connection.rollbacks == 1


def test_append_get_list_and_idempotency(monkeypatch: pytest.MonkeyPatch) -> None:
    event = _event()
    payload = event.to_json()
    connections = [
        _Connection([{"ok": 1}, None]),
        _Connection([{"ok": 1}, {"event_json": payload}]),
        _Connection([{"event_json": payload}]),
        _Connection([{"event_json": payload}]),
    ]
    store = PostgresAuditStore.__new__(PostgresAuditStore)
    monkeypatch.setattr(store, "_connect", lambda: connections.pop(0))
    workspace = WorkspaceId("workspace-1")
    assert store.append(workspace, event) == event
    assert store.append(workspace, event) == event
    assert store.get(workspace, event.id) == event
    assert store.list_for_resource(
        workspace,
        resource_kind="workspace_resource",
        resource_ref="workspace/project:project-1",
    ) == (event,)
    with pytest.raises(ValueError, match="between 1 and 1000"):
        store.list_for_resource(workspace, resource_kind="x", resource_ref="y", limit=0)
