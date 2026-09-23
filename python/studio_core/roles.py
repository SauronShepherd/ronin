"""Named, provider-neutral roles compiled to typed authorization grants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .grants import Action, Grant, GrantSet, ResourceScope

RoleName = Literal["viewer", "editor", "owner"]


@dataclass(frozen=True, slots=True)
class RoleDefinition:
    name: RoleName
    description: str
    grants: GrantSet


def _actions(*values: Action) -> frozenset[Action]:
    return frozenset(values)


def role_definition(name: RoleName, *, resource: ResourceScope) -> RoleDefinition:
    """Return the canonical role for one explicit resource scope."""
    if name == "viewer":
        actions = _actions("read", "list", "evidence:read")
        description = "Read and inspect the scoped resource."
    elif name == "editor":
        actions = _actions("read", "list", "events", "write", "submit", "evidence:read")
        description = "Read and modify the scoped resource without administration."
    elif name == "owner":
        actions = _actions(
            "read", "list", "events", "write", "submit", "execute", "cancel", "evidence:read"
        )
        description = "Full operational control of the scoped resource."
    else:
        raise ValueError("unsupported role name")
    return RoleDefinition(name, description, GrantSet((Grant(actions, resource),)))


def role_names() -> tuple[RoleName, ...]:
    return ("viewer", "editor", "owner")


__all__ = ("RoleDefinition", "RoleName", "role_definition", "role_names")
