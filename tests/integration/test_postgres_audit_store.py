from __future__ import annotations

import os
from uuid import uuid4

import pytest

_DSN = os.environ.get("RONIN_TEST_POSTGRES_DSN")
if not _DSN:
    pytest.skip("RONIN_TEST_POSTGRES_DSN is not configured", allow_module_level=True)

psycopg = pytest.importorskip("psycopg")

from studio_core import Workspace, WorkspaceId
from studio_core.audit import AuditActor, AuditEvent, AuditEventId, AuditResource
from studio_orchestrator import Instant
from studio_storage import PostgresAuditStore, PostgresMetadataStore
from studio_storage.audit import AuditConflict
from studio_storage.workspaces import WorkspaceNotFound

_NOW = Instant("2026-09-14T04:00:00.000000Z")


def _workspace() -> Workspace:
    suffix = uuid4().hex
    return Workspace(WorkspaceId(f"audit-test-{suffix}"), f"Audit Test {suffix}")


def _event(identifier: str, occurred_at: str, *, action: str = "authorize:job.read") -> AuditEvent:
    return AuditEvent(
        AuditEventId(identifier),
        occurred_at,
        AuditActor("user", "principal-1"),
        action,
        AuditResource("workspace_resource", "workspace/project:project-1"),
        "allowed",
        f"req-{identifier}",
        (("decision_reason", "role_permission_allowed"),),
    )


def _cleanup(workspace_id: WorkspaceId) -> None:
    with psycopg.connect(_DSN, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM ronin_workspaces WHERE workspace_id=%s", (workspace_id.value,))


def test_postgres_audit_round_trip_idempotency_and_conflict() -> None:
    metadata = PostgresMetadataStore(_DSN, application_name="ronin-audit-test-metadata")
    workspace = _workspace()
    metadata.create_workspace(workspace, now=_NOW)
    store = PostgresAuditStore(_DSN, application_name="ronin-audit-test")
    event = _event(
        f"audit-{uuid4().hex}",
        "2026-09-14T04:00:01.000000Z",
    )

    try:
        assert store.append(workspace.id, event) == event
        assert store.append(workspace.id, event) == event
        assert store.get(workspace.id, event.id) == event

        conflicting = _event(
            event.id.value,
            event.occurred_at,
            action="authorize:job.submit",
        )
        with pytest.raises(AuditConflict):
            store.append(workspace.id, conflicting)
        assert store.get(workspace.id, event.id) == event
    finally:
        _cleanup(workspace.id)


def test_postgres_audit_resource_listing_is_newest_first_and_bounded() -> None:
    metadata = PostgresMetadataStore(_DSN, application_name="ronin-audit-test-metadata")
    workspace = _workspace()
    metadata.create_workspace(workspace, now=_NOW)
    store = PostgresAuditStore(_DSN, application_name="ronin-audit-test")
    older = _event(f"audit-{uuid4().hex}", "2026-09-14T04:00:01.000000Z")
    newer = _event(f"audit-{uuid4().hex}", "2026-09-14T04:00:02.000000Z")

    try:
        store.append(workspace.id, older)
        store.append(workspace.id, newer)
        listed = store.list_for_resource(
            workspace.id,
            resource_kind="workspace_resource",
            resource_ref="workspace/project:project-1",
            limit=10,
        )
        assert listed == (newer, older)
        assert store.list_for_resource(
            workspace.id,
            resource_kind="workspace_resource",
            resource_ref="workspace/project:project-1",
            limit=1,
        ) == (newer,)
        for invalid in (0, 1001):
            with pytest.raises(ValueError, match="between 1 and 1000"):
                store.list_for_resource(
                    workspace.id,
                    resource_kind="workspace_resource",
                    resource_ref="workspace/project:project-1",
                    limit=invalid,
                )
    finally:
        _cleanup(workspace.id)


def test_postgres_audit_rejects_unknown_workspace() -> None:
    PostgresMetadataStore(_DSN, application_name="ronin-audit-test-metadata")
    store = PostgresAuditStore(_DSN, application_name="ronin-audit-test")
    missing = WorkspaceId(f"missing-{uuid4().hex}")
    event = _event(f"audit-{uuid4().hex}", "2026-09-14T04:00:03.000000Z")

    with pytest.raises(WorkspaceNotFound):
        store.append(missing, event)


def test_postgres_audit_database_check_rejects_invalid_outcome() -> None:
    metadata = PostgresMetadataStore(_DSN, application_name="ronin-audit-test-metadata")
    workspace = _workspace()
    metadata.create_workspace(workspace, now=_NOW)
    PostgresAuditStore(_DSN, application_name="ronin-audit-test")

    try:
        with psycopg.connect(_DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                with pytest.raises(psycopg.errors.CheckViolation) as violation:
                    cursor.execute(
                        "INSERT INTO ronin_audit_events("
                        "workspace_id,audit_event_id,occurred_at,actor_kind,actor_ref,action,"
                        "resource_kind,resource_ref,outcome,request_id,digest,event_json) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            workspace.id.value,
                            f"audit-invalid-{uuid4().hex}",
                            "2026-09-14T04:00:04.000000Z",
                            "user",
                            "principal-1",
                            "authorize:test",
                            "workspace_resource",
                            "workspace/project:project-1",
                            "invalid",
                            None,
                            "0" * 64,
                            "{}",
                        ),
                    )
                assert violation.value.sqlstate == "23514"
    finally:
        _cleanup(workspace.id)
