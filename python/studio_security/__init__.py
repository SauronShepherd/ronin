"""Single-operator authorization, audit, redaction and service identity support."""

from .audit import audit_actor, authorization_audit_event, mutation_audit_event
from .classification_policy import (
    Classification,
    ClassificationDecision,
    ClassificationPolicy,
    evaluate_classification_policy,
)
from .context import actor_context, current_actor, require_actor
from .contracts import (
    PERMISSIONS,
    Actor,
    Permission,
    PolicyDecision,
    PolicyRequirement,
    Principal,
    PrincipalId,
    PrincipalKind,
)
from .policy_actions import PolicyAction, PolicyActionResult, evaluate_policy_action
from .redaction import redact
from .service_identity import (
    ServiceIdentityError,
    ServiceIdentityLifecycle,
    ServiceIdentityTransition,
)
from .store import IdentityConflict, SqliteServiceIdentityStore

__all__ = (
    "Actor",
    "Classification",
    "ClassificationDecision",
    "ClassificationPolicy",
    "IdentityConflict",
    "PERMISSIONS",
    "Permission",
    "PolicyAction",
    "PolicyActionResult",
    "PolicyDecision",
    "PolicyRequirement",
    "Principal",
    "PrincipalId",
    "PrincipalKind",
    "ServiceIdentityError",
    "ServiceIdentityLifecycle",
    "ServiceIdentityTransition",
    "SqliteServiceIdentityStore",
    "actor_context",
    "audit_actor",
    "authorization_audit_event",
    "current_actor",
    "evaluate_classification_policy",
    "evaluate_policy_action",
    "mutation_audit_event",
    "redact",
    "require_actor",
)
