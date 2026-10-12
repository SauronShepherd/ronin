from __future__ import annotations

import pytest
from studio_core.grants import (
    ACTIONS,
    MAX_CONSTRAINTS,
    MAX_GRANTS,
    Decision,
    Grant,
    GrantSet,
    Requirement,
    ResourceScope,
    parse_bearer_scope,
    requirement_to_bearer_scope,
)


def _requirement(action: str = "read", kind: str = "project", identifier: str | None = "p-1"):
    return Requirement(action, ResourceScope(kind, identifier))


def test_resource_scope_rejects_global_identifiers_and_invalid_payload_shapes() -> None:
    with pytest.raises(ValueError, match="global resource scope"):
        ResourceScope("*", "not-global")
    with pytest.raises(ValueError, match="exactly kind and identifier"):
        ResourceScope.from_payload({"kind": "project"})
    with pytest.raises(ValueError, match="invalid field types"):
        ResourceScope.from_payload({"kind": "project", "identifier": 1})


@pytest.mark.parametrize("kind", ["project", "job", "run", "evidence", "*"])
def test_every_resource_kind_round_trips(kind: str) -> None:
    scope = ResourceScope(kind, None)
    assert ResourceScope.from_payload(scope.to_payload()) == scope


def test_requirement_version_and_action_are_fail_closed() -> None:
    with pytest.raises(ValueError, match="unsupported authorization requirement version"):
        Requirement("read", ResourceScope("project", None), version=2)
    with pytest.raises(ValueError, match="unsupported authorization action"):
        Requirement("admin", ResourceScope("project", None))  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [None, 1, [], {}])
def test_grant_vocabularies_reject_non_text_values_with_value_error(value: object) -> None:
    with pytest.raises(ValueError, match="unsupported authorization action"):
        Requirement(value, ResourceScope("project", None))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unsupported authorization resource kind"):
        ResourceScope(value, None)  # type: ignore[arg-type]


@pytest.mark.parametrize("action", sorted(ACTIONS))
def test_every_authorization_action_round_trips(action: str) -> None:
    requirement = _requirement(action)
    assert Requirement.from_payload(requirement.to_payload()) == requirement


def test_constraint_tuple_and_mapping_inputs_are_canonicalized() -> None:
    grant_from_mapping = Grant(
        frozenset({"read"}),
        ResourceScope("project", None),
        {"zeta": "last", "alpha": "first"},
    )
    grant_from_tuple = Grant(
        frozenset({"read"}),
        ResourceScope("project", None),
        (("alpha", "first"), ("zeta", "last")),
    )
    assert grant_from_mapping.constraints == grant_from_tuple.constraints
    assert grant_from_mapping.to_payload()["constraints"] == {
        "alpha": "first",
        "zeta": "last",
    }


@pytest.mark.parametrize(
    "constraints",
    [
        {"x": " "},
        {"x": "line\nvalue"},
        {"x": "\x00"},
        {"api-key": "safe-looking"},
        {"team": "Bearer token"},
        {"team": "-----BEGIN PRIVATE KEY-----"},
    ],
)
def test_constraint_validation_rejects_text_duplicates_and_credentials(constraints) -> None:
    with pytest.raises(ValueError, match="."):
        Grant(frozenset({"read"}), ResourceScope("project", None), constraints)


def test_constraint_keys_are_case_sensitive_but_sorted() -> None:
    grant = Grant(
        frozenset({"read"}),
        ResourceScope("project", None),
        {"x": "value", "X": "other"},
    )
    assert grant.constraints == (("X", "other"), ("x", "value"))


def test_constraint_limit_is_exact_and_duplicate_tuple_keys_are_rejected() -> None:
    valid = {f"k{i}": str(i) for i in range(MAX_CONSTRAINTS)}
    assert len(Grant(frozenset({"read"}), ResourceScope("project", None), valid).constraints) == (
        MAX_CONSTRAINTS
    )
    with pytest.raises(ValueError, match="at most"):
        Grant(
            frozenset({"read"}),
            ResourceScope("project", None),
            {f"k{i}": str(i) for i in range(MAX_CONSTRAINTS + 1)},
        )
    with pytest.raises(ValueError, match="keys must be unique"):
        Grant(
            frozenset({"read"}),
            ResourceScope("project", None),
            (("team", "a"), ("team", "b")),
        )


def test_grant_set_rejects_duplicate_grants_and_preserves_canonical_order() -> None:
    first = Grant(frozenset({"write"}), ResourceScope("project", "b"))
    second = Grant(frozenset({"read"}), ResourceScope("project", "a"))
    assert GrantSet((first, second)).grants == (second, first)
    with pytest.raises(ValueError, match="must be unique"):
        GrantSet((first, first))
    with pytest.raises(ValueError, match="at most"):
        GrantSet(
            tuple(
                Grant(frozenset({"read"}), ResourceScope("project", str(index)))
                for index in range(MAX_GRANTS + 1)
            )
        )


def test_grant_set_decision_distinguishes_unsupported_constraints_and_ambiguity() -> None:
    requirement = _requirement()
    constrained = Grant(frozenset({"read"}), requirement.resource, {"tenant": "analytics"})
    assert GrantSet((constrained,)).permits(requirement) == Decision(
        False, "unsupported_constraints"
    )
    first = Grant(frozenset({"read"}), requirement.resource)
    second = Grant(frozenset({"read", "write"}), requirement.resource)
    decision = GrantSet((first, second)).permits(requirement)
    assert decision.allowed is False
    assert decision.reason == "ambiguous"
    assert decision.matched_grant is None


@pytest.mark.parametrize(
    ("grant_scope", "requirement_scope", "covered"),
    [
        (ResourceScope("*", None), ResourceScope("job", "j"), True),
        (ResourceScope("project", None), ResourceScope("project", "p"), True),
        (ResourceScope("project", "p"), ResourceScope("project", "p"), True),
        (ResourceScope("project", "p"), ResourceScope("project", "q"), False),
        (ResourceScope("project", "p"), ResourceScope("job", "p"), False),
        (ResourceScope("project", "p"), ResourceScope("project", None), False),
    ],
)
def test_resource_coverage_boundaries(
    grant_scope: ResourceScope, requirement_scope: ResourceScope, covered: bool
) -> None:
    grant = Grant(frozenset({"read"}), grant_scope)
    assert GrantSet((grant,)).permits(Requirement("read", requirement_scope)).allowed is covered


def test_exact_resource_ids_filters_action_kind_and_constraints() -> None:
    grants = GrantSet(
        (
            Grant(frozenset({"read"}), ResourceScope("project", "z")),
            Grant(frozenset({"read"}), ResourceScope("project", "a")),
            Grant(frozenset({"write"}), ResourceScope("project", "ignored")),
            Grant(frozenset({"read"}), ResourceScope("job", "ignored")),
            Grant(
                frozenset({"read"}),
                ResourceScope("project", "constrained"),
                {"team": "x"},
            ),
        )
    )
    assert grants.exact_resource_ids("read", kind="project") == ("a", "z")
    assert grants.exact_resource_ids("write", kind="project") == ("ignored",)
    assert grants.exact_resource_ids("read", kind="evidence") == ()


def test_exact_resource_ids_returns_canonical_ids_and_wildcard_precedence() -> None:
    grants = GrantSet(
        (
            Grant(frozenset({"read"}), ResourceScope("project", "z")),
            Grant(frozenset({"read"}), ResourceScope("project", "a")),
            Grant(frozenset({"read"}), ResourceScope("project", None)),
        )
    )
    assert grants.exact_resource_ids("read", kind="project") is None
    assert grants.exact_resource_ids("write", kind="project") == ()


@pytest.mark.parametrize(
    "identifier",
    ["a/b", "a b", "a:b", "ümlaut"],
)
def test_bearer_scope_percent_encoding_is_round_trip_and_canonical(identifier: str) -> None:
    requirement = _requirement("evidence:read", "evidence", identifier)
    encoded = requirement_to_bearer_scope(requirement)
    assert parse_bearer_scope(encoded) == requirement
    assert "%" in encoded


@pytest.mark.parametrize(
    "value",
    [
        "ronin:v1:read:project:p-1:extra",
        "ronin:v2:read:project:p-1",
        "other:v1:read:project:p-1",
        "ronin:v1:admin:project:p-1",
        "ronin:v1:read:unknown:p-1",
        "ronin:v1:read:project:",
        "ronin:v1:read:project:%2A",
        "ronin:v1:read:project:p%ZZ",
    ],
)
def test_bearer_scope_parser_rejects_noncanonical_forms(value: str) -> None:
    with pytest.raises(ValueError, match="."):
        parse_bearer_scope(value)


@pytest.mark.parametrize("action", sorted(ACTIONS))
@pytest.mark.parametrize("kind", ["project", "job", "run", "evidence", "*"])
def test_bearer_scope_round_trips_every_action_and_global_resource_kind(
    action: str, kind: str
) -> None:
    requirement = _requirement(action, kind, None)
    encoded = requirement_to_bearer_scope(requirement)
    assert encoded.endswith(":*")
    assert parse_bearer_scope(encoded) == requirement


@pytest.mark.parametrize(
    "value",
    [
        "ronin:v1:read%ZZ:project:p-1",
        "ronin:v1:read:project%ZZ:p-1",
        "ronin:v1:read:project:%2f1",
        "ronin:v1:read:project:p+1",
        "ronin:v1:read:project:p%20-1",
    ],
)
def test_bearer_scope_parser_rejects_noncanonical_component_encoding(value: str) -> None:
    with pytest.raises(ValueError, match="."):
        parse_bearer_scope(value)


def test_grant_set_json_parser_rejects_invalid_json_and_preserves_payload_defaults() -> None:
    with pytest.raises(ValueError, match="must be valid JSON"):
        GrantSet.from_json("not-json")
    grant = Grant(frozenset({"read"}), ResourceScope("project", "p-1"))
    restored = GrantSet.from_json(GrantSet((grant,)).to_json())
    assert restored.requirements() == grant.requirements()


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"version": 1, "actions": "read", "resource": {"kind": "project", "identifier": None}},
        {"version": 1, "actions": ["read"], "resource": []},
        {"version": 1, "actions": ["read"], "resource": {"kind": "project", "identifier": None}, "constraints": []},
    ],
)
def test_grant_payload_parser_rejects_each_invalid_top_level_shape(payload: object) -> None:
    with pytest.raises(ValueError, match="authorization grant"):
        Grant.from_payload(payload)
