"""Explicit single-user authentication and authorization for local control plane."""

from __future__ import annotations

from studio_core import WorkspaceId
from studio_security import (
    Actor,
    Permission,
    PolicyDecision,
    PolicyRequirement,
    Principal,
    PrincipalId,
)


class StaticControlPlaneAuthenticator:
    """Authenticate exactly one configured local control-plane bearer token."""

    def __init__(self, token: str, *, principal_id: str = "local-control-plane") -> None:
        if not token or token != token.strip() or "\n" in token or "\r" in token:
            raise ValueError("control-plane token must be non-empty and single-line")
        self._authorization = f"Bearer {token}"
        self._actor = Actor(
            Principal(
                PrincipalId(principal_id), "user", "Local control plane", "local", principal_id
            ),
            auth_method="static",
        )

    def authenticate(self, authorization: str | None) -> Actor | None:
        return self._actor if authorization == self._authorization else None


class StaticControlPlaneAuthorizer:
    """Authorize only the configured workspace and explicit permission set."""

    def __init__(self, workspace_id: WorkspaceId, permissions: frozenset[Permission]) -> None:
        if not permissions:
            raise ValueError("control-plane permissions must not be empty")
        self._workspace_id = workspace_id
        self._permissions = permissions

    def authorize(self, actor: Actor, requirement: PolicyRequirement) -> PolicyDecision:
        del actor
        if requirement.workspace_id != self._workspace_id:
            return PolicyDecision(False, "workspace_not_configured")
        if requirement.permission not in self._permissions:
            return PolicyDecision(False, "permission_not_configured")
        return PolicyDecision(True, "static_permission_allowed", ("admin",))


__all__ = ("StaticControlPlaneAuthenticator", "StaticControlPlaneAuthorizer")
