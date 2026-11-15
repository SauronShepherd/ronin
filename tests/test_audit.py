from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from studio_core import Workspace, WorkspaceId
from studio_core.audit import AuditActor, AuditEvent, AuditEventId, AuditResource, _metadata
from studio_orchestrator import Instant
from studio_storage.audit import AuditConflict, AuditIntegrityError, SqliteAuditStore
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


def test_audit_store_reopens_and_rejects_tampered_payload(tmp_path: Path) -> None:
    path = tmp_path / "ronin.sqlite3"
    event = _event()
    _store(path).append(WorkspaceId("ws-1"), event)

    tampered = _event(action="workspace.delete").to_json()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE audit_events SET event_json=? WHERE workspace_id=? AND audit_event_id=?",
            (tampered, "ws-1", event.id.value),
        )

    reopened = SqliteAuditStore(path, migration_now=_NOW)
    with pytest.raises(AuditIntegrityError, match="columns do not match|digest mismatch"):
        reopened.get(WorkspaceId("ws-1"), event.id)
    with pytest.raises(AuditIntegrityError, match="columns do not match|digest mismatch"):
        reopened.append(WorkspaceId("ws-1"), event)


def test_audit_store_rejects_tampered_denormalized_columns(tmp_path: Path) -> None:
    path = tmp_path / "ronin.sqlite3"
    event = _event()
    _store(path).append(WorkspaceId("ws-1"), event)

    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE audit_events SET action=? WHERE workspace_id=? AND audit_event_id=?",
            ("workspace.delete", "ws-1", event.id.value),
        )

    with pytest.raises(AuditIntegrityError, match="columns do not match"):
        SqliteAuditStore(path, migration_now=_NOW).list_for_resource(
            WorkspaceId("ws-1"), resource_kind="workspace", resource_ref="ws-1"
        )


def test_audit_store_lists_workspace_events_newest_first_and_bounded(tmp_path: Path) -> None:
    store = _store(tmp_path / "ronin.sqlite3")
    workspace_id = WorkspaceId("ws-1")
    for identifier in ("audit-1", "audit-2", "audit-3"):
        store.append(workspace_id, _event(identifier))

    assert store.list_for_workspace(workspace_id, limit=2) == (
        _event("audit-3"),
        _event("audit-2"),
    )
    assert store.list_for_workspace(workspace_id, limit=2, offset=2) == (_event("audit-1"),)
    for invalid in (0, 1001):
        with pytest.raises(ValueError, match="between 1 and 1000"):
            store.list_for_workspace(workspace_id, limit=invalid)
    with pytest.raises(ValueError, match="non-negative"):
        store.list_for_workspace(workspace_id, offset=-1)


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "secret",
        "token",
        "credential",
        "api_key",
        "authorization",
        "cookie",
        "private_key",
        "client_secret",
    ],
)
def test_audit_metadata_rejects_secret_keys(key: str) -> None:
    with pytest.raises(ValueError, match="credential-bearing"):
        AuditEvent(
            id=AuditEventId("audit-1"),
            occurred_at=str(_NOW),
            actor=AuditActor("local", "local-operator"),
            action="connection.test",
            resource=AuditResource("connection", "c1"),
            outcome="succeeded",
            metadata=((key, "not-allowed"),),
        )


@pytest.mark.parametrize(
    "key",
    [
        "PASSWORD",
        "SeCrEt",
        "TOKEN",
        "Credential",
        "API_KEY",
        "Authorization",
        "COOKIE",
        "Private_Key",
        "CLIENT_SECRET",
    ],
)
def test_audit_metadata_rejects_secret_keys_case_insensitively(key: str) -> None:
    with pytest.raises(
        ValueError,
        match="^audit metadata must not contain credential-bearing keys$",
    ):
        _metadata(((key, "not-allowed"),))


@pytest.mark.parametrize(
    "value", ["", " leading", "trailing ", "line\nfeed", "line\rfeed", "nul\x00byte"]
)
def test_audit_metadata_rejects_unportable_values(value: str) -> None:
    with pytest.raises(ValueError, match="non-empty, trimmed"):
        _metadata((("source", value),))


def test_audit_metadata_rejects_credential_material_and_duplicate_keys() -> None:
    for value in ("Bearer abc123", "-----BEGIN PRIVATE KEY-----"):
        with pytest.raises(
            ValueError,
            match="^audit metadata must not contain credential material$",
        ):
            _metadata((("source", value),))
    with pytest.raises(ValueError, match="keys must be unique"):
        _metadata((("source", "one"), ("source", "two")))


def test_audit_metadata_is_sorted_and_does_not_alias_input() -> None:
    values = [("z-key", "last"), ("a-key", "first")]
    result = _metadata(tuple(values))
    values.reverse()
    assert result == (("a-key", "first"), ("z-key", "last"))


def test_audit_metadata_preserves_exact_context_for_invalid_key_and_value() -> None:
    with pytest.raises(ValueError, match=".") as key_error:
        _metadata((("bad\nkey", "value"),))
    assert str(key_error.value) == "audit metadata key must be non-empty, trimmed, and single-line"

    with pytest.raises(ValueError, match=".") as value_error:
        _metadata((("key", "bad\rvalue"),))
    assert str(value_error.value) == (
        "audit metadata value must be non-empty, trimmed, and single-line"
    )


@pytest.mark.parametrize(
    "key",
    [
        "prefix-PASSWORD-suffix",
        "prefix-SECRET-suffix",
        "prefix-TOKEN-suffix",
        "prefix-CREDENTIAL-suffix",
        "prefix-API_KEY-suffix",
        "prefix-AUTHORIZATION-suffix",
        "prefix-COOKIE-suffix",
        "prefix-PRIVATE_KEY-suffix",
        "prefix-CLIENT_SECRET-suffix",
    ],
)
def test_audit_metadata_rejects_sensitive_markers_inside_keys(key: str) -> None:
    with pytest.raises(
        ValueError,
        match="^audit metadata must not contain credential-bearing keys$",
    ):
        _metadata(((key, "public-value"),))


@pytest.mark.parametrize("value", ["bearer token", "-----begin private key-----"])
def test_audit_metadata_rejects_each_credential_material_marker(value: str) -> None:
    with pytest.raises(
        ValueError,
        match="^audit metadata must not contain credential material$",
    ):
        _metadata((("source", value),))


@pytest.mark.parametrize(
    "value",
    ["", " leading", "trailing ", "line\nfeed", "line\rfeed", "nul\x00byte"],
)
def test_audit_identity_and_resource_text_reject_unportable_values(value: str) -> None:
    with pytest.raises(ValueError, match="non-empty|single-line"):
        AuditEventId(value)
    with pytest.raises(ValueError, match="non-empty|single-line"):
        AuditActor("local", value)
    with pytest.raises(ValueError, match="non-empty|single-line"):
        AuditResource("workspace", value)
    with pytest.raises(ValueError, match="non-empty|single-line"):
        AuditResource(value, "ws-1")


@pytest.mark.parametrize(
    "field",
    ["action", "request_id"],
)
@pytest.mark.parametrize("value", ["", " leading", "trailing ", "line\nfeed", "nul\x00byte"])
def test_audit_event_text_fields_reject_unportable_values(field: str, value: str) -> None:
    values: dict[str, object] = {"action": "connection.test", "request_id": "request-1"}
    values[field] = value
    with pytest.raises(ValueError, match="non-empty|single-line"):
        AuditEvent(
            id=AuditEventId("audit-invalid-text"),
            occurred_at=str(_NOW),
            actor=AuditActor("local", "local-operator"),
            action=values["action"],
            resource=AuditResource("connection", "c1"),
            outcome="succeeded",
            request_id=values["request_id"],
        )


def test_audit_event_round_trip_preserves_canonical_payload_and_digest() -> None:
    event = AuditEvent(
        id=AuditEventId("audit-round-trip"),
        occurred_at=str(_NOW),
        actor=AuditActor("service", "svc-1"),
        action="workspace.update",
        resource=AuditResource("workspace", "ws-1"),
        outcome="allowed",
        request_id="request-round-trip",
        metadata=(("z-key", "last"), ("a-key", "first")),
    )

    restored = AuditEvent.from_json(event.to_json())

    assert restored == event
    assert restored.to_json() == event.to_json()
    assert restored.digest == event.digest


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "local"},
        {"kind": "local", "ref": 1},
        {"kind": "unknown", "ref": "operator"},
    ],
)
def test_audit_actor_payload_validation_is_fail_closed(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="audit actor|unsupported"):
        AuditActor.from_payload(payload)


@pytest.mark.parametrize("occurred_at", ["2026-09-12", "2026-09-12T00:00:00+00:00", " "])
def test_audit_event_timestamp_validation_is_fail_closed(occurred_at: str) -> None:
    with pytest.raises(ValueError, match="audit occurred_at"):
        AuditEvent(
            id=AuditEventId("audit-invalid-time"),
            occurred_at=occurred_at,
            actor=AuditActor("local", "local-operator"),
            action="workspace.create",
            resource=AuditResource("workspace", "ws-1"),
            outcome="succeeded",
        )


def test_list_for_resource_is_scoped(tmp_path: Path) -> None:
    store = _store(tmp_path / "ronin.sqlite3")
    event = _event()
    store.append(WorkspaceId("ws-1"), event)

    assert store.list_for_resource(
        WorkspaceId("ws-1"), resource_kind="workspace", resource_ref="ws-1"
    ) == (event,)
    assert (
        store.list_for_resource(WorkspaceId("ws-1"), resource_kind="connection", resource_ref="c1")
        == ()
    )
