import json
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
