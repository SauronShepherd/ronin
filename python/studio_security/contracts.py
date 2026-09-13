"""Multi-user identity, actor and workspace RBAC contracts for Ronin Public v1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from studio_core import WorkspaceId

PrincipalKind: TypeAlias = Literal["user", "service"]
SubjectKind: TypeAlias = Literal["principal", "group"]
WorkspaceRole: TypeAlias = Literal["admin", "operator", "editor", "viewer"]
Permission: TypeAlias = Literal[
    "workspace.read",
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
    "genai.read",
    "genai.write",
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
        "genai.read",
        "genai.write",
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

ROLE_PERMISSIONS: dict[WorkspaceRole, frozenset[Permission]] = {
    "viewer": frozenset(
        {
            "workspace.read",
            "project.read",
            "git.read",
            "job.read",
            "scheduler.read",
            "connection.read",
            "catalog.read",
            "quality.read",
            "ml.read",
            "genai.read",
            "semantic.read",
            "stream.read",
            "observability.read",
            "finops.read",
        }
    ),
    "operator": frozenset(
        {
            "workspace.read",
            "project.read",
            "git.read",
            "job.read",
            "job.submit",
            "job.cancel",
            "scheduler.read",
            "scheduler.write",
            "connection.read",
            "catalog.read",
            "quality.read",
            "ml.read",
            "genai.read",
            "semantic.read",
            "stream.read",
            "stream.write",
            "observability.read",
            "finops.read",
            "secret.use",
        }
    ),
    "editor": frozenset(
        permission
        for permission in PERMISSIONS
        if permission not in {"workspace.admin", "audit.read"}
    ),
    "admin": frozenset(PERMISSIONS),
}


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


@dataclass(frozen=True, order=True, slots=True)
class GroupId:
    value: str

    def __post_init__(self) -> None:
        _text(self.value, "group id")

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
class Group:
    id: GroupId
    name: str

    def __post_init__(self) -> None:
        _text(self.name, "group name")


@dataclass(frozen=True, order=True, slots=True)
class RoleBinding:
    workspace_id: WorkspaceId
    subject_kind: SubjectKind
    subject_id: str
    role: WorkspaceRole

    def __post_init__(self) -> None:
        if self.subject_kind not in {"principal", "group"}:
            raise ValueError("role binding subject_kind must be principal or group")
        _text(self.subject_id, "role binding subject_id")
        if self.role not in {"admin", "operator", "editor", "viewer"}:
            raise ValueError("unsupported workspace role")


@dataclass(frozen=True, slots=True)
class Actor:
    principal: Principal
    groups: tuple[GroupId, ...] = ()
    auth_method: str = "oidc"

    def __post_init__(self) -> None:
        groups = tuple(sorted(set(self.groups)))
        object.__setattr__(self, "groups", groups)
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
    matched_roles: tuple[WorkspaceRole, ...] = ()

    def __post_init__(self) -> None:
        _text(self.reason, "policy decision reason")
        roles = tuple(sorted(set(self.matched_roles)))
        object.__setattr__(self, "matched_roles", roles)
        if self.allowed and not roles:
            raise ValueError("allowed policy decision requires a matched role")


__all__ = (
    "Actor",
    "Group",
    "GroupId",
    "PERMISSIONS",
    "Permission",
    "PolicyDecision",
    "PolicyRequirement",
    "Principal",
    "PrincipalId",
    "PrincipalKind",
    "ROLE_PERMISSIONS",
    "RoleBinding",
    "SubjectKind",
    "WorkspaceRole",
)
