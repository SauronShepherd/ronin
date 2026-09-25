from __future__ import annotations

from itertools import permutations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from studio_core.grants import (
    ACTIONS,
    MAX_CONSTRAINTS,
    AuthorizationEvidence,
    Decision,
    Grant,
    GrantSet,
    Requirement,
    ResourceScope,
    parse_bearer_scope,
    requirement_to_bearer_scope,
)


def _requirement() -> Requirement:
    return Requirement("read", ResourceScope("project", "p-1"))


def test_resource_and_requirement_validation_is_closed() -> None:
    with pytest.raises(ValueError, match="unsupported authorization resource"):
        ResourceScope("unknown", None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="identifier"):
        ResourceScope("*", "p-1")
    with pytest.raises(ValueError, match="exactly"):
        ResourceScope.from_payload({"kind": "project", "identifier": "p", "extra": 1})
    with pytest.raises(ValueError, match="unsupported authorization action"):
        Requirement("unknown", ResourceScope("project", None))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="version"):
        Requirement("read", ResourceScope("project", None), version=2)


@pytest.mark.parametrize("value", ["", " p", "p ", "p\n", "p\r", "p\x00"])
def test_text_and_constraint_validation_fails_closed(value: str) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        ResourceScope("project", value)
    with pytest.raises(ValueError, match="non-empty|credential"):
        Grant(frozenset({"read"}), ResourceScope("project", "p"), {value: "x"})


def test_constraints_reject_secrets_duplicates_and_excess() -> None:
    for key in ("token", "private_key"):
        with pytest.raises(ValueError, match="credential"):
            Grant(frozenset({"read"}), ResourceScope("project", None), {key: "x"})
    with pytest.raises(ValueError, match="credential"):
        Grant(frozenset({"read"}), ResourceScope("project", None), {"x": "Bearer abc"})
    with pytest.raises(ValueError, match="unique"):
        Grant(frozenset({"read"}), ResourceScope("project", None), (("x", "1"), ("x", "2")))
    values = {f"k{i}": "v" for i in range(MAX_CONSTRAINTS + 1)}
    with pytest.raises(ValueError, match="at most"):
        Grant(frozenset({"read"}), ResourceScope("project", None), values)


@pytest.mark.parametrize("action", sorted(ACTIONS))
def test_grant_action_vocabulary_is_fail_closed(action: str) -> None:
    grant = Grant(frozenset({action}), ResourceScope("project", "p-1"))
    assert action in grant.actions
    with pytest.raises(ValueError, match="unsupported authorization action"):
        Grant(frozenset({"not-an-action"}), ResourceScope("project", "p-1"))


def test_constraints_are_sorted_and_secret_detection_is_case_insensitive() -> None:
    grant = Grant(
        frozenset({"read"}),
        ResourceScope("project", "p-1"),
        {"zeta": "last", "alpha": "first"},
    )
    assert grant.constraints == (("alpha", "first"), ("zeta", "last"))
    assert Grant.from_payload(grant.to_payload()) == grant
    for key, value in (
        ("Api-Key", "x"),
        ("safe", "-----BEGIN PRIVATE KEY-----secret"),
        ("safe", "Bearer token"),
    ):
        with pytest.raises(ValueError, match="credential"):
            Grant(frozenset({"read"}), ResourceScope("project", None), {key: value})


def test_grant_set_decisions_and_specificity_are_deterministic() -> None:
    exact = Grant(frozenset({"read"}), ResourceScope("project", "p-1"))
    wildcard = Grant(frozenset({"read"}), ResourceScope("project", None))
    global_grant = Grant(frozenset({"read"}), ResourceScope("*", None))
    constrained = Grant(frozenset({"read"}), ResourceScope("project", "p-1"), {"tenant": "x"})
    assert GrantSet((exact, wildcard)).permits(_requirement()).matched_grant == exact
    assert GrantSet((global_grant,)).permits(_requirement()).reason == "allowed"
    assert GrantSet((constrained,)).permits(_requirement()).reason == "unsupported_constraints"
    assert GrantSet(()).permits(_requirement()).reason == "no_matching_grant"
    with pytest.raises(ValueError, match="unique"):
        GrantSet((exact, exact))
    for order in permutations((exact, wildcard, global_grant)):
        assert (
            GrantSet(order).permits(_requirement()).to_payload()
            == GrantSet((exact, wildcard, global_grant)).permits(_requirement()).to_payload()
        )


@given(st.permutations(("read", "list", "events")))
def test_grant_order_never_changes_decision(actions: tuple[str, ...]) -> None:
    grants = tuple(
        Grant(frozenset({action}), ResourceScope("project", "p-1")) for action in actions
    )
    requirement = Requirement("read", ResourceScope("project", "p-1"))
    decisions = {
        GrantSet(order).permits(requirement).to_payload().__repr__()
        for order in permutations(grants)
    }
    assert len(decisions) == 1


def test_bearer_scope_round_trip_and_canonical_encoding() -> None:
    requirement = Requirement("evidence:read", ResourceScope("project", "a/b"))
    encoded = requirement_to_bearer_scope(requirement)
    assert parse_bearer_scope(encoded) == requirement
    with pytest.raises(ValueError, match="canonical"):
        parse_bearer_scope(encoded.replace("%2F", "%2f"))
    with pytest.raises(ValueError, match="percent"):
        parse_bearer_scope("ronin:v1:read:project:p%ZZ")


@pytest.mark.parametrize(
    "value",
    [
        "ronin:v1:read:project",
        "ronin:v2:read:project:p-1",
        "other:v1:read:project:p-1",
        "ronin:v1:unknown:project:p-1",
        "ronin:v1:read:unknown:p-1",
        "ronin:v1:read:project:",
        "ronin:v1:read:project:%2A",
        "ronin:v1:read:project:p-1:extra",
        "ronin:v1:read:project:p%2f1",
    ],
)
def test_bearer_scope_rejects_noncanonical_or_malformed_shapes(value: str) -> None:
    with pytest.raises(ValueError, match="bearer scope|unsupported|canonical"):
        parse_bearer_scope(value)


@pytest.mark.parametrize("value", [None, 1, [], {}])
def test_bearer_scope_requires_text(value: object) -> None:
    with pytest.raises(ValueError, match="bearer scope"):
        parse_bearer_scope(value)  # type: ignore[arg-type]


def test_bearer_scope_preserves_wildcard_identifier_semantics() -> None:
    requirement = parse_bearer_scope("ronin:v1:read:project:*")
    assert requirement.resource.identifier is None
    assert requirement_to_bearer_scope(requirement) == "ronin:v1:read:project:*"


def test_decision_and_evidence_invariants() -> None:
    grant = Grant(frozenset({"read"}), ResourceScope("project", "p-1"))
    with pytest.raises(ValueError, match="matched"):
        Decision(True, "allowed", None)
    with pytest.raises(ValueError, match="denied"):
        Decision(False, "allowed", grant)
    evidence = AuthorizationEvidence(
        "http", _requirement(), GrantSet((grant,)).permits(_requirement())
    )
    assert evidence.to_payload()["version"] == 1
    with pytest.raises(ValueError, match="enforcement"):
        AuthorizationEvidence("", _requirement(), evidence.decision)


def test_action_vocabulary_is_nonempty() -> None:
    assert ACTIONS
