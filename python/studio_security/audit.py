"""Bridge multi-user security decisions into the existing append-only audit contract."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import cast

from studio_core.audit import AuditActor, AuditEvent, AuditEventId, AuditOutcome, AuditResource
from studio_orchestrator import Instant

from .contracts import Actor, PolicyDecision, PolicyRequirement
from .redaction import redact


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


def mutation_audit_event(
    actor: Actor,
    *,
    workspace_id: str,
    action: str,
    resource_ref: str,
    outcome: AuditOutcome = "succeeded",
    metadata: dict[str, object] | None = None,
    now: Instant | str,
    request_id: str | None = None,
) -> AuditEvent:
    """Build a deterministic, bounded and redacted mutation audit event."""
    if not action or not resource_ref or outcome not in {"succeeded", "failed"}:
        raise ValueError("invalid mutation audit fields")
    occurred_at = str(Instant(now))
    safe_metadata = redact(metadata or {}, max_depth=3, max_items=32)
    seed = "\n".join(
        (
            actor.principal.id.value,
            workspace_id,
            action,
            resource_ref,
            outcome,
            occurred_at,
            request_id or "",
        )
    )
    identifier = AuditEventId(
        "audit-mutation-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]
    )
    pairs = [("workspace_id", workspace_id), ("mutation", action)]
    metadata_items = safe_metadata.items() if isinstance(safe_metadata, Mapping) else ()
    pairs.extend(
        (str(key), str(value))
        for key, value in metadata_items
        if not any(
            term in str(key).casefold()
            for term in ("password", "secret", "token", "credential", "api_key")
        )
    )
    return AuditEvent(
        identifier,
        occurred_at,
        audit_actor(actor),
        action,
        AuditResource("workspace_resource", f"{workspace_id}/{resource_ref}"),
        cast(AuditOutcome, outcome),
        request_id,
        tuple(pairs),
    )


__all__ = ("audit_actor", "authorization_audit_event", "mutation_audit_event")
