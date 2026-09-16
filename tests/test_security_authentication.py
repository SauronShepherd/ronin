from studio_security import Actor, Principal, PrincipalId, RbacAuthorizer, authenticate_actor


class _Validator:
    def authenticate_principal(self, token, _store):
        assert token == "valid"  # noqa: S105 - deterministic fixture credential
        return _store.principal


class _Identities:
    principal = Principal(PrincipalId("alice"), "user", "Alice", "https://issuer", "sub")

    def find_principal(self, issuer, subject):
        assert (issuer, subject) == (self.principal.issuer, self.principal.subject)
        return self.principal


class _Rbac:
    def groups_for_principal(self, _principal_id):
        return ()

    def roles_for_actor(self, _workspace_id, _principal_id, _groups):
        return ()


def test_authenticate_actor_composes_validator_and_authoritative_rbac() -> None:
    actor = authenticate_actor("valid", _Validator(), _Identities(), RbacAuthorizer(_Rbac()))
    assert isinstance(actor, Actor)
    assert actor.principal.id == PrincipalId("alice")
    assert actor.auth_method == "oidc"
