"""Persistable role assignments for users, groups, and service identities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .grants import GrantSet, ResourceScope
from .roles import RoleName, role_definition

PrincipalKind = Literal["user", "group", "service"]


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty trimmed text")
    if any(char in value for char in "\r\n\x00"):
        raise ValueError(f"{name} must be single-line text")
    return value


@dataclass(frozen=True, slots=True, order=True)
class Principal:
    kind: PrincipalKind
    identifier: str

    def __post_init__(self) -> None:
        if self.kind not in {"user", "group", "service"}:
            raise ValueError("unsupported principal kind")
        _text(self.identifier, "principal identifier")


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    principal: Principal
    role: RoleName
    scope: ResourceScope

    def __post_init__(self) -> None:
        if self.role not in {"viewer", "editor", "owner"}:
            raise ValueError("unsupported role name")

    @property
    def grants(self) -> GrantSet:
        return role_definition(self.role, resource=self.scope).grants

    def to_payload(self) -> dict[str, object]:
        return {
            "principal": {
                "kind": self.principal.kind,
                "identifier": self.principal.identifier,
            },
            "role": self.role,
            "scope": self.scope.to_payload(),
        }


__all__ = ("Principal", "PrincipalKind", "RoleAssignment")
