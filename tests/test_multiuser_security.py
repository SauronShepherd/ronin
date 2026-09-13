import json
import sqlite3
import time
from pathlib import Path

import pytest

from studio_core import WorkspaceId
from studio_security import (
    Actor,
    Group,
    GroupId,
    OidcConfig,
    OidcTokenValidator,
    PolicyRequirement,
    Principal,
    PrincipalId,
    RbacAuthorizer,
    RoleBinding,
    SqliteIdentityStore,
    actor_context,
    current_actor,
)


class _Keys:
    def __init__(self, payload):
        self.payload = payload

    def jwks(self):
        return self.payload


def _principal() -> Principal:
    return Principal(
        PrincipalId("alice"),
        "user",
        "Alice",
        "https://issuer.example",
        "oidc-alice",
        "alice@example.com",
    )


def test_group_role_grants_workspace_permission(tmp_path: Path) -> None:
    store = SqliteIdentityStore(tmp_path / "security.sqlite")
    principal = store.put_principal(_principal())
    group = store.put_group(Group(GroupId("engineers"), "Engineers"))
    store.add_group_member(group.id, principal.id)
    store.put_role_binding(
        RoleBinding(WorkspaceId("workspace"), "group", group.id.value, "editor")
    )
    authorizer = RbacAuthorizer(store)
    actor = authorizer.actor(principal)
    allowed = authorizer.authorize(
        actor,
        PolicyRequirement(WorkspaceId("workspace"), "catalog.write", "asset:orders"),
    )
    assert allowed.allowed
    assert allowed.matched_roles == ("editor",)
    denied = authorizer.authorize(
        actor,
        PolicyRequirement(WorkspaceId("workspace"), "audit.read"),
    )
    assert not denied.allowed


def test_sqlite_role_binding_constraints_reject_malformed_direct_writes(tmp_path: Path) -> None:
    path = tmp_path / "security.sqlite"
    store = SqliteIdentityStore(path)
    principal = store.put_principal(_principal())
    store.put_role_binding(
        RoleBinding(WorkspaceId("workspace"), "principal", principal.id.value, "viewer")
    )

    connection = sqlite3.connect(path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO security_role_bindings(workspace_id,subject_kind,subject_id,role) "
                "VALUES (?,?,?,?)",
                ("workspace", "external", principal.id.value, "viewer"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO security_role_bindings(workspace_id,subject_kind,subject_id,role) "
                "VALUES (?,?,?,?)",
                ("workspace", "principal", principal.id.value, "owner"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE security_role_bindings SET role='owner' WHERE workspace_id='workspace'"
            )
    finally:
        connection.close()


def test_existing_role_binding_table_gains_validation_triggers(tmp_path: Path) -> None:
    path = tmp_path / "security.sqlite"
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE security_principals (
                principal_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                display_name TEXT NOT NULL,
                issuer TEXT NOT NULL,
                subject TEXT NOT NULL,
                email TEXT,
                active INTEGER NOT NULL,
                UNIQUE(issuer, subject)
            );
            CREATE TABLE security_groups (
                group_id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE security_group_members (
                group_id TEXT NOT NULL REFERENCES security_groups(group_id) ON DELETE CASCADE,
                principal_id TEXT NOT NULL REFERENCES security_principals(principal_id) ON DELETE CASCADE,
                PRIMARY KEY(group_id, principal_id)
            );
            CREATE TABLE security_role_bindings (
                workspace_id TEXT NOT NULL,
                subject_kind TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                role TEXT NOT NULL,
                PRIMARY KEY(workspace_id, subject_kind, subject_id, role)
            );
            """
        )
        connection.commit()
    finally:
        connection.close()

    SqliteIdentityStore(path)

    connection = sqlite3.connect(path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="invalid security role binding"):
            connection.execute(
                "INSERT INTO security_role_bindings(workspace_id,subject_kind,subject_id,role) "
                "VALUES ('workspace','principal','alice','owner')"
            )
    finally:
        connection.close()


def test_actor_context_is_request_local() -> None:
    actor = Actor(_principal())
    assert current_actor() is None
    with actor_context(actor):
        assert current_actor() == actor
    assert current_actor() is None


def test_oidc_validator_verifies_signature_issuer_and_audience() -> None:
    jwt = pytest.importorskip("jwt")
    cryptography = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.rsa")
    private_key = cryptography.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk["kid"] = "key-1"
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": "https://issuer.example",
            "sub": "oidc-alice",
            "aud": "ronin",
            "iat": now,
            "exp": now + 300,
            "name": "Alice",
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "key-1"},
    )
    validator = OidcTokenValidator(
        OidcConfig("https://issuer.example", "ronin", ("RS256",)),
        _Keys({"keys": [public_jwk]}),
    )
    claims = validator.authenticate_claims(token)
    assert claims.subject == "oidc-alice"
    assert claims.audience == ("ronin",)


def test_unprovisioned_oidc_subject_fails_closed(tmp_path: Path) -> None:
    jwt = pytest.importorskip("jwt")
    cryptography = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.rsa")
    private_key = cryptography.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk["kid"] = "key-1"
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": "https://issuer.example",
            "sub": "unknown",
            "aud": "ronin",
            "iat": now,
            "exp": now + 300,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "key-1"},
    )
    validator = OidcTokenValidator(
        OidcConfig("https://issuer.example", "ronin", ("RS256",)),
        _Keys({"keys": [public_jwk]}),
    )
    store = SqliteIdentityStore(tmp_path / "security.sqlite")
    with pytest.raises(PermissionError, match="not provisioned"):
        validator.authenticate_principal(token, store)
