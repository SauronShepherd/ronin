"""Bridge multi-user security decisions into the existing append-only audit contract."""

from __future__ import annotations

import hashlib

from studio_core.audit import AuditActor, AuditEvent, AuditEventId, AuditResource
from studio_orchestrator import Instant

from .contracts import Actor, PolicyDecision, PolicyRequirement


def audit_actor(actor: Actor) -> AuditActor:
    return AuditActor(actor.principal.kind, actor.principal.id.value)


def authorization_audit_event(
    actor: Actor,
    requirement: PolicyRequirement,
    decision: PolicyDecision,
    *,
    now: Instant | str,
    request_id: str | None = None,
) -> AuditEvent:
    occurred_at = str(Instant(now))
    resource_ref = requirement.workspace_id.value
    if requirement.resource_ref is not None:
        resource_ref += f"/{requirement.resource_ref}"
    seed = "\n".join(
        (
            actor.principal.id.value,
            requirement.workspace_id.value,
            requirement.permission,
            requirement.resource_ref or "",
            str(decision.allowed),
            decision.reason,
            occurred_at,
            request_id or "",
        )
    )
    identifier = AuditEventId(
        "audit-authz-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]
    )
    metadata = (
        ("auth_method", actor.auth_method),
        ("decision_reason", decision.reason),
        ("roles", ",".join(decision.matched_roles) or "none"),
        ("workspace_id", requirement.workspace_id.value),
    )
    return AuditEvent(
        identifier,
        occurred_at,
        audit_actor(actor),
        f"authorize:{requirement.permission}",
        AuditResource("workspace_resource", resource_ref),
        "allowed" if decision.allowed else "denied",
        request_id,
        metadata,
    )


__all__ = ("audit_actor", "authorization_audit_event")
