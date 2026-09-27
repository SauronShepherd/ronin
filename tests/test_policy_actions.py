from studio_core import WorkspaceId
from studio_security import (
    Actor,
    ClassificationPolicy,
    PolicyDecision,
    PolicyRequirement,
    Principal,
    PrincipalId,
    evaluate_policy_action,
)


def test_policy_action_fails_closed_for_restricted_classification():
    result = evaluate_policy_action(
        _actor(),
        PolicyRequirement(WorkspaceId("ws"), "workspace.read", "asset:customers"),
        action="block-new-work",
        resource_ref="asset:customers",
        authorize=lambda _actor, _requirement: PolicyDecision(
            True, "role_permission_allowed", ("admin",)
        ),
        classification="restricted",
        classification_policy=ClassificationPolicy(
            maximum="restricted", explicit_high_sensitivity=True
        ),
    )
    assert not result.decision.allowed
    assert result.decision.reason == "explicit_high_sensitivity_grant_required"


def _actor() -> Actor:
    return Actor(Principal(PrincipalId("user-1"), "user", "User", "issuer", "subject"))


def test_policy_action_is_authorized_and_audit_ready():
    result = evaluate_policy_action(
        _actor(),
        PolicyRequirement(WorkspaceId("ws"), "workspace.read", "job-1"),
        action="require-approval",
        resource_ref="job-1",
        authorize=lambda _actor, _requirement: PolicyDecision(True, "role matched", ("owner",)),
    )
    assert result.decision.allowed is True
    assert result.audit_action == "policy.require-approval"
    assert result.to_payload()["schema"].endswith("/v1")
