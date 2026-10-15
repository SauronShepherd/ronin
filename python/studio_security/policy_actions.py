"""Authorization-aware operational policy actions with audit-ready evidence."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from .classification_policy import ClassificationPolicy, evaluate_classification_policy
from .contracts import Actor, PolicyDecision, PolicyRequirement

PolicyAction = Literal["warn", "block-new-work", "require-approval"]


@dataclass(frozen=True, slots=True)
class PolicyActionResult:
    schema: str
    action: PolicyAction
    resource_ref: str
    decision: PolicyDecision
    audit_action: str

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "action": self.action,
            "resource_ref": self.resource_ref,
            "allowed": self.decision.allowed,
            "reason": self.decision.reason,
            "matched_roles": list(self.decision.matched_roles),
            "audit_action": self.audit_action,
        }


def evaluate_policy_action(
    actor: Actor,
    requirement: PolicyRequirement,
    *,
    action: PolicyAction,
    resource_ref: str,
    authorize: Callable[[Actor, PolicyRequirement], PolicyDecision],
    classification: str | None = None,
    classification_policy: ClassificationPolicy | None = None,
    explicit_high_sensitivity_grant: bool = False,
) -> PolicyActionResult:
    """Evaluate an action through the supplied RBAC authorizer, never bypassing it."""
    if action not in {"warn", "block-new-work", "require-approval"}:
        raise ValueError("unsupported policy action")
    if not resource_ref or resource_ref != resource_ref.strip() or "\x00" in resource_ref:
        raise ValueError("resource_ref must be non-empty and trimmed")
    if requirement.resource_ref not in {None, resource_ref}:
        raise ValueError("policy requirement resource does not match action resource")
    if classification_policy is not None:
        classification_decision = evaluate_classification_policy(
            classification=classification,
            resource_ref=resource_ref,
            policy=classification_policy,
            explicit_high_sensitivity_grant=explicit_high_sensitivity_grant,
        )
        if not classification_decision.allowed:
            return PolicyActionResult(
                "ronin.security.policy-action/v1",
                action,
                resource_ref,
                PolicyDecision(False, classification_decision.reason),
                f"policy.{action}",
            )
    decision = authorize(actor, requirement)
    if not isinstance(decision, PolicyDecision):
        raise TypeError("authorize must return PolicyDecision")
    return PolicyActionResult(
        "ronin.security.policy-action/v1",
        action,
        resource_ref,
        decision,
        f"policy.{action}",
    )


__all__ = ("PolicyAction", "PolicyActionResult", "evaluate_policy_action")
