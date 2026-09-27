"""Multi-user identity, OIDC, RBAC and actor propagation for Ronin Public v1."""

from .audit import audit_actor, authorization_audit_event, mutation_audit_event
from .authentication import PrincipalAuthenticator, authenticate_actor
from .classification_policy import (
    Classification,
    ClassificationDecision,
    ClassificationPolicy,
    evaluate_classification_policy,
)
from .context import actor_context, current_actor, require_actor
from .contracts import (
    PERMISSIONS,
    ROLE_PERMISSIONS,
    Actor,
    Group,
    GroupId,
    Permission,
    PolicyDecision,
    PolicyRequirement,
    Principal,
    PrincipalId,
    PrincipalKind,
    RoleBinding,
    SubjectKind,
    WorkspaceRole,
)
from .jwks_file import FileJwksProvider, JwksFileError
from .oidc import (
    JwksProvider,
    OidcAuthenticationError,
    OidcClaims,
    OidcConfig,
    OidcDependencyError,
    OidcPrincipalStore,
    OidcTokenValidator,
)
from .oidc_discovery import HttpsOidcJwksProvider, OidcDiscoveryError
from .policy_actions import PolicyAction, PolicyActionResult, evaluate_policy_action
from .postgres_store import PostgresIdentityStore, PostgresSecurityDependencyError
from .rbac import RbacAuthorizer, RbacStore
from .redaction import redact
from .service_identity import (
    ServiceIdentityError,
    ServiceIdentityLifecycle,
    ServiceIdentityTransition,
)
from .store import IdentityConflict, SqliteIdentityStore

__all__ = (
    "Actor",
    "Classification",
    "ClassificationDecision",
    "ClassificationPolicy",
    "PrincipalAuthenticator",
    "FileJwksProvider",
    "Group",
    "GroupId",
    "HttpsOidcJwksProvider",
    "IdentityConflict",
    "JwksFileError",
    "JwksProvider",
    "OidcAuthenticationError",
    "OidcClaims",
    "OidcConfig",
    "OidcDependencyError",
    "OidcDiscoveryError",
    "OidcPrincipalStore",
    "OidcTokenValidator",
    "PERMISSIONS",
    "Permission",
    "PolicyDecision",
    "PolicyRequirement",
    "PolicyAction",
    "PolicyActionResult",
    "PostgresIdentityStore",
    "PostgresSecurityDependencyError",
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
    "authenticate_actor",
    "authorization_audit_event",
    "mutation_audit_event",
    "evaluate_classification_policy",
    "evaluate_policy_action",
    "redact",
    "ServiceIdentityError",
    "ServiceIdentityLifecycle",
    "ServiceIdentityTransition",
    "current_actor",
    "require_actor",
)
