"""Multi-user identity, OIDC, RBAC and actor propagation for Ronin Public v1."""

from .audit import audit_actor, authorization_audit_event
from .context import actor_context, current_actor, require_actor
from .contracts import (
    Actor,
    Group,
    GroupId,
    PERMISSIONS,
    Permission,
    PolicyDecision,
    PolicyRequirement,
    Principal,
    PrincipalId,
    PrincipalKind,
    ROLE_PERMISSIONS,
    RoleBinding,
    SubjectKind,
    WorkspaceRole,
)
from .oidc import (
    JwksProvider,
    OidcAuthenticationError,
    OidcClaims,
    OidcConfig,
    OidcDependencyError,
    OidcPrincipalStore,
    OidcTokenValidator,
)
from .rbac import RbacAuthorizer, RbacStore
from .store import IdentityConflict, SqliteIdentityStore

__all__ = (
    "Actor",
    "Group",
    "GroupId",
    "IdentityConflict",
    "JwksProvider",
    "OidcAuthenticationError",
    "OidcClaims",
    "OidcConfig",
    "OidcDependencyError",
    "OidcPrincipalStore",
    "OidcTokenValidator",
    "PERMISSIONS",
    "Permission",
    "PolicyDecision",
    "PolicyRequirement",
    "Principal",
    "PrincipalId",
    "PrincipalKind",
    "ROLE_PERMISSIONS",
    "RbacAuthorizer",
    "RbacStore",
    "RoleBinding",
    "SqliteIdentityStore",
    "SubjectKind",
    "WorkspaceRole",
    "actor_context",
    "audit_actor",
    "authorization_audit_event",
    "current_actor",
    "require_actor",
)
