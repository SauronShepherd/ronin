import pytest
from studio_security import ClassificationPolicy, evaluate_classification_policy


def test_high_sensitivity_is_fail_closed_without_explicit_grant():
    decision = evaluate_classification_policy(
        classification="restricted",
        resource_ref="asset:customers",
        policy=ClassificationPolicy(maximum="restricted", explicit_high_sensitivity=True),
    )
    assert not decision.allowed
    assert decision.reason == "explicit_high_sensitivity_grant_required"


def test_missing_or_unknown_classification_is_denied():
    policy = ClassificationPolicy()
    assert not evaluate_classification_policy(
        classification=None, resource_ref="asset:x", policy=policy
    ).allowed


def test_classification_policy_rejects_malformed_resource_or_flag():
    with pytest.raises(TypeError, match="boolean"):
        ClassificationPolicy(explicit_high_sensitivity=1)  # type: ignore[arg-type]
    policy = ClassificationPolicy()
    for resource in (" asset:x", "asset:x\n"):
        decision = evaluate_classification_policy(
            classification="public", resource_ref=resource, policy=policy
        )
        assert not decision.allowed
        assert not decision.allowed
    assert not evaluate_classification_policy(
        classification="top-secret", resource_ref="asset:x", policy=policy
    ).allowed
