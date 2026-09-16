"""Authentication composition for OIDC principals and authoritative RBAC actors."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .contracts import Actor, Principal
from .oidc import OidcPrincipalStore, OidcTokenValidator
from .rbac import RbacAuthorizer


@runtime_checkable
class PrincipalAuthenticator(Protocol):
    def authenticate_principal(self, token: str, store: OidcPrincipalStore) -> Principal: ...


def authenticate_actor(
    token: str,
    validator: OidcTokenValidator,
    identities: OidcPrincipalStore,
    rbac: RbacAuthorizer,
) -> Actor:
    """Validate an OIDC token, require provisioning, and hydrate current groups from storage."""

    principal = validator.authenticate_principal(token, identities)
    return rbac.actor(principal, auth_method="oidc")


__all__ = ("PrincipalAuthenticator", "authenticate_actor")
