from __future__ import annotations

import os
from uuid import uuid4

import pytest

from studio_core import WorkspaceId
from studio_security import (
    Actor,
    Group,
    GroupId,
    IdentityConflict,
    PolicyRequirement,
    PostgresIdentityStore,
    Principal,
    PrincipalId,
    RbacAuthorizer,
    RoleBinding,
)

_DSN = os.environ.get("RONIN_TEST_POSTGRES_DSN")
if not _DSN:
    pytest.skip(
        "RONIN_TEST_POSTGRES_DSN is required for PostgreSQL security integration tests",
        allow_module_level=True,
    )


def _prefix() -> str:
    return f"security-{uuid4().hex}"


def _principal(prefix: str, *, subject: str = "subject") -> Principal:
    return Principal(
        PrincipalId(f"{prefix}-principal"),
        "user",
        "Postgres User",
        "https://issuer.example",
        f"{prefix}-{subject}",
        f"{prefix}@example.test",
    )


def test_postgres_identity_preserves_stable_external_binding() -> None:
    store = PostgresIdentityStore(_DSN, application_name="ronin-security-test")
    prefix = _prefix()
    principal = _principal(prefix)
    assert store.put_principal(principal) == principal
    assert store.get_principal(principal.id) == principal
    assert store.find_principal(principal.issuer, principal.subject) == principal

    renamed = Principal(
        principal.id,
        principal.kind,
        "Renamed User",
        principal.issuer,
        principal.subject,
        principal.email,
        False,
    )
    assert store.put_principal(renamed) == renamed
    assert store.get_principal(principal.id) == renamed

    rebound = Principal(
        principal.id,
        principal.kind,
        principal.display_name,
        principal.issuer,
        f"{prefix}-different-subject",
        principal.email,
    )
    with pytest.raises(IdentityConflict):
        store.put_principal(rebound)

    other = Principal(
        PrincipalId(f"{prefix}-other"),
        "user",
        "Other",
        principal.issuer,
        principal.subject,
    )
    with pytest.raises(IdentityConflict):
        store.put_principal(other)


def test_postgres_group_membership_is_authoritative_for_rbac() -> None:
    store = PostgresIdentityStore(_DSN, application_name="ronin-security-test")
    prefix = _prefix()
    workspace = WorkspaceId(f"{prefix}-workspace")
    principal = store.put_principal(_principal(prefix))
    group = store.put_group(Group(GroupId(f"{prefix}-admins"), "Admins"))
    store.put_role_binding(RoleBinding(workspace, "group", group.id.value, "admin"))
    authorizer = RbacAuthorizer(store)

    forged = Actor(principal, (group.id,))
    denied = authorizer.authorize(forged, PolicyRequirement(workspace, "audit.read"))
    assert not denied.allowed
    assert denied.reason == "no_workspace_role"

    store.add_group_member(group.id, principal.id)
    actor = authorizer.actor(principal)
    allowed = authorizer.authorize(actor, PolicyRequirement(workspace, "audit.read"))
    assert allowed.allowed
    assert allowed.matched_roles == ("admin",)

    assert store.remove_group_member(group.id, principal.id)
    revoked = authorizer.authorize(actor, PolicyRequirement(workspace, "audit.read"))
    assert not revoked.allowed
    assert revoked.reason == "no_workspace_role"


def test_postgres_direct_roles_and_missing_subject_behavior() -> None:
    store = PostgresIdentityStore(_DSN, application_name="ronin-security-test")
    prefix = _prefix()
    workspace = WorkspaceId(f"{prefix}-workspace")
    principal = store.put_principal(_principal(prefix))
    binding = RoleBinding(workspace, "principal", principal.id.value, "viewer")
    assert store.put_role_binding(binding) == binding
    assert store.put_role_binding(binding) == binding
    assert store.roles_for_actor(workspace, principal.id) == ("viewer",)
    assert store.delete_role_binding(binding)
    assert not store.delete_role_binding(binding)

    missing = RoleBinding(workspace, "principal", f"{prefix}-missing", "viewer")
    with pytest.raises(KeyError, match="does not exist"):
        store.put_role_binding(missing)


def test_postgres_role_binding_database_checks_reject_invalid_values() -> None:
    psycopg = pytest.importorskip("psycopg")
    PostgresIdentityStore(_DSN, application_name="ronin-security-test")
    prefix = _prefix()

    connection = psycopg.connect(_DSN, autocommit=False)
    try:
        with connection.cursor() as cursor:
            with pytest.raises(Exception) as invalid_kind:
                cursor.execute(
                    "INSERT INTO ronin_security_role_bindings("
                    "workspace_id,subject_kind,subject_id,role) VALUES (%s,%s,%s,%s)",
                    (f"{prefix}-workspace", "forged", "subject", "viewer"),
                )
            assert getattr(invalid_kind.value, "sqlstate", None) == "23514"
        connection.rollback()

        with connection.cursor() as cursor:
            with pytest.raises(Exception) as invalid_role:
                cursor.execute(
                    "INSERT INTO ronin_security_role_bindings("
                    "workspace_id,subject_kind,subject_id,role) VALUES (%s,%s,%s,%s)",
                    (f"{prefix}-workspace", "principal", "subject", "owner"),
                )
            assert getattr(invalid_role.value, "sqlstate", None) == "23514"
        connection.rollback()
    finally:
        connection.close()
