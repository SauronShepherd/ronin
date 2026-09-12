from __future__ import annotations

from pathlib import Path

import pytest

from studio_core import Workspace, WorkspaceId
from studio_core.audit import AuditActor, AuditEvent, AuditEventId, AuditResource
from studio_orchestrator import Instant
from studio_storage.audit import AuditConflict, SqliteAuditStore
from studio_storage.workspaces import SqliteWorkspaceStore

_NOW = Instant("2026-09-12T00:00:00.000000Z")


def _event(event_id: str = "audit-1", *, action: str = "workspace.create") -> AuditEvent:
    return AuditEvent(
        id=AuditEventId(event_id),
        occurred_at=str(_NOW),
        actor=AuditActor("local", "local-operator"),
        action=action,
        resource=AuditResource("workspace", "ws-1"),
        outcome="succeeded",
        request_id="request-1",
        metadata=(("source", "test"),),
    )


def _store(path: Path) -> SqliteAuditStore:
    workspaces = SqliteWorkspaceStore(path, migration_now=_NOW)
    workspaces.create_workspace(Workspace(WorkspaceId("ws-1"), "Workspace"), now=_NOW)
    return SqliteAuditStore(path, migration_now=_NOW)


def test_audit_store_is_idempotent_for_same_event(tmp_path: Path) -> None:
    store = _store(tmp_path / "ronin.sqlite3")
    event = _event()

    assert store.append(WorkspaceId("ws-1"), event) == event
    assert store.append(WorkspaceId("ws-1"), event) == event
    assert store.get(WorkspaceId("ws-1"), event.id) == event


def test_audit_event_id_conflict_fails_closed(tmp_path: Path) -> None:
    store = _store(tmp_path / "ronin.sqlite3")
    store.append(WorkspaceId("ws-1"), _event())

    with pytest.raises(AuditConflict):
        store.append(WorkspaceId("ws-1"), _event(action="workspace.delete"))


def test_audit_metadata_rejects_secret_keys() -> None:
    with pytest.raises(ValueError, match="credential-bearing"):
        AuditEvent(
            id=AuditEventId("audit-1"),
            occurred_at=str(_NOW),
            actor=AuditActor("local", "local-operator"),
            action="connection.test",
            resource=AuditResource("connection", "c1"),
            outcome="succeeded",
            metadata=(("api_key", "not-allowed"),),
        )


def test_list_for_resource_is_scoped(tmp_path: Path) -> None:
    store = _store(tmp_path / "ronin.sqlite3")
    event = _event()
    store.append(WorkspaceId("ws-1"), event)

    assert store.list_for_resource(
        WorkspaceId("ws-1"), resource_kind="workspace", resource_ref="ws-1"
    ) == (event,)
    assert store.list_for_resource(
        WorkspaceId("ws-1"), resource_kind="connection", resource_ref="c1"
    ) == ()
