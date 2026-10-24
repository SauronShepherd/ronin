"""Single-operator authorization and audit contracts for Ronin Public v1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from studio_core import WorkspaceId

PrincipalKind: TypeAlias = Literal["user", "service"]
Permission: TypeAlias = Literal[
    "workspace.read",
    "workspace.write",
    "workspace.admin",
    "project.read",
    "project.write",
    "git.read",
    "git.write",
    "job.read",
    "job.submit",
    "job.cancel",
    "scheduler.read",
    "scheduler.write",
    "connection.read",
    "connection.write",
    "catalog.read",
    "catalog.write",
    "quality.read",
    "quality.write",
    "ml.read",
    "ml.write",
    "semantic.read",
    "semantic.write",
    "stream.read",
    "stream.write",
    "observability.read",
    "finops.read",
    "finops.write",
    "secret.use",
    "audit.read",
]

PERMISSIONS: frozenset[str] = frozenset(
    {
        "workspace.read",
        "workspace.write",
        "workspace.admin",
        "project.read",
        "project.write",
        "git.read",
        "git.write",
        "job.read",
        "job.submit",
        "job.cancel",
        "scheduler.read",
        "scheduler.write",
        "connection.read",
        "connection.write",
        "catalog.read",
        "catalog.write",
        "quality.read",
        "quality.write",
        "ml.read",
        "ml.write",
        "semantic.read",
        "semantic.write",
        "stream.read",
        "stream.write",
        "observability.read",
        "finops.read",
        "finops.write",
        "secret.use",
        "audit.read",
    }
)


def _text(value: str, name: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    return value


@dataclass(frozen=True, order=True, slots=True)
class PrincipalId:
    value: str

    def __post_init__(self) -> None:
        _text(self.value, "principal id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Principal:
    id: PrincipalId
    kind: PrincipalKind
    display_name: str
    issuer: str
    subject: str
    email: str | None = None
    active: bool = True

    def __post_init__(self) -> None:
        if self.kind not in {"user", "service"}:
            raise ValueError("principal kind must be user or service")
        _text(self.display_name, "principal display_name")
        _text(self.issuer, "principal issuer")
        _text(self.subject, "principal subject")
        if self.email is not None:
            _text(self.email, "principal email")


@dataclass(frozen=True, slots=True)
class Actor:
    principal: Principal
    auth_method: str = "static"

    def __post_init__(self) -> None:
        _text(self.auth_method, "actor auth_method")
        if not self.principal.active:
            raise ValueError("inactive principal cannot become an actor")


@dataclass(frozen=True, slots=True)
class PolicyRequirement:
    workspace_id: WorkspaceId
    permission: Permission
    resource_ref: str | None = None

    def __post_init__(self) -> None:
        if self.permission not in PERMISSIONS:
            raise ValueError("unsupported security permission")
        if self.resource_ref is not None:
            _text(self.resource_ref, "policy resource_ref")


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    reason: str
    matched_permissions: tuple[Permission, ...] = ()

    def __post_init__(self) -> None:
        _text(self.reason, "policy decision reason")
        if any(permission not in PERMISSIONS for permission in self.matched_permissions):
            raise ValueError("policy decision contains an unsupported permission")
        permissions = tuple(sorted(set(self.matched_permissions)))
        object.__setattr__(self, "matched_permissions", permissions)
        if self.allowed and not permissions:
            raise ValueError("allowed policy decision requires a matched permission")


__all__ = (
    "Actor",
    "PERMISSIONS",
    "Permission",
    "PolicyDecision",
    "PolicyRequirement",
    "Principal",
    "PrincipalId",
    "PrincipalKind",
)
