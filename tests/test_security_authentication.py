from studio_security import Actor, Principal, PrincipalId, RbacAuthorizer, authenticate_actor


class _Validator:
    def authenticate_principal(self, token, store):
        assert token == "valid"
        return store.principal


class _Identities:
    principal = Principal(PrincipalId("alice"), "user", "Alice", "https://issuer", "sub")

    def find_principal(self, issuer, subject):
        assert (issuer, subject) == (self.principal.issuer, self.principal.subject)
        return self.principal


class _Rbac:
    def groups_for_principal(self, principal_id):
        return ()

    def roles_for_actor(self, workspace_id, principal_id, groups):
        return ()


def test_authenticate_actor_composes_validator_and_authoritative_rbac() -> None:
    actor = authenticate_actor("valid", _Validator(), _Identities(), RbacAuthorizer(_Rbac()))
    assert isinstance(actor, Actor)
    assert actor.principal.id == PrincipalId("alice")
    assert actor.auth_method == "oidc"
