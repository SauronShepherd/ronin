"""Explicit single-user authentication and authorization for local control plane."""

from __future__ import annotations

from threading import RLock

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
    """Authorize known local workspaces using one operator's explicit permissions."""

    def __init__(self, workspace_id: WorkspaceId, permissions: frozenset[Permission]) -> None:
        if not permissions:
            raise ValueError("control-plane permissions must not be empty")
        self._workspace_ids = {workspace_id}
        self._permissions = permissions
        self._lock = RLock()

    def register_workspace(self, workspace_id: WorkspaceId) -> None:
        """Add a workspace created in this local installation to the operator scope."""
        with self._lock:
            self._workspace_ids.add(workspace_id)

    def authorize(self, actor: Actor, requirement: PolicyRequirement) -> PolicyDecision:
        del actor
        with self._lock:
            workspace_is_known = requirement.workspace_id in self._workspace_ids
        if not workspace_is_known:
            return PolicyDecision(False, "workspace_not_configured")
        if requirement.permission not in self._permissions:
            return PolicyDecision(False, "permission_not_configured")
        return PolicyDecision(True, "static_permission_allowed", (requirement.permission,))


__all__ = ("StaticControlPlaneAuthenticator", "StaticControlPlaneAuthorizer")
