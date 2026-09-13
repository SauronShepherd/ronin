"""Deny-by-default workspace RBAC policy evaluation."""

from __future__ import annotations

from typing import Protocol, cast, runtime_checkable

from studio_core import WorkspaceId

from .contracts import (
    Actor,
    GroupId,
    PolicyDecision,
    PolicyRequirement,
    Principal,
    PrincipalId,
    ROLE_PERMISSIONS,
    WorkspaceRole,
)


@runtime_checkable
class RbacStore(Protocol):
    def groups_for_principal(self, principal_id: PrincipalId) -> tuple[GroupId, ...]: ...

    def roles_for_actor(
        self,
        workspace_id: WorkspaceId,
        principal_id: PrincipalId,
        groups: tuple[GroupId, ...],
    ) -> tuple[str, ...]: ...


class RbacAuthorizer:
    def __init__(self, store: RbacStore) -> None:
        self._store = store

    def actor(self, principal: Principal, *, auth_method: str = "oidc") -> Actor:
        groups = self._store.groups_for_principal(principal.id)
        return Actor(principal, groups, auth_method)

    def authorize(self, actor: Actor, requirement: PolicyRequirement) -> PolicyDecision:
        roles_raw = self._store.roles_for_actor(
            requirement.workspace_id,
            actor.principal.id,
            actor.groups,
        )
        roles: list[WorkspaceRole] = []
        for value in roles_raw:
            if value not in ROLE_PERMISSIONS:
                continue
            roles.append(cast(WorkspaceRole, value))
        matched = tuple(
            sorted(role for role in roles if requirement.permission in ROLE_PERMISSIONS[role])
        )
        if matched:
            return PolicyDecision(True, "role_permission_allowed", matched)
        if not roles:
            return PolicyDecision(False, "no_workspace_role")
        return PolicyDecision(False, "role_does_not_grant_permission")

    def require(self, actor: Actor, requirement: PolicyRequirement) -> PolicyDecision:
        decision = self.authorize(actor, requirement)
        if not decision.allowed:
            raise PermissionError(
                f"permission denied: {requirement.permission} in {requirement.workspace_id} "
                f"({decision.reason})"
            )
        return decision


__all__ = ("RbacAuthorizer", "RbacStore")
