from __future__ import annotations

import pytest
from studio_core import (
    InstanceAnchor,
    OwnershipMetadata,
    allocate_instance_keys,
    ownership,
)
from studio_core.transport_policy import BIND_POLICIES, parse_bind_policy
from studio_core.versions import compare_releases, parse_comparable_release


def test_instance_allocation_duplicate_error_is_exact() -> None:
    anchor = InstanceAnchor("authoring", "node-1")
    with pytest.raises(ValueError, match=".") as error:
        allocate_instance_keys((anchor, anchor))
    assert str(error.value) == "instance anchors must be unique within an allocation batch"


def test_ownership_refs_reject_empty_and_duplicate_references() -> None:
    with pytest.raises(ValueError, match=".") as empty_error:
        ownership._refs(("   ",), "steward_refs")
    assert str(empty_error.value) == "steward_refs must contain unique non-empty references"

    with pytest.raises(ValueError, match=".") as duplicate_error:
        ownership._refs(("user/a", "user/a"), "steward_refs")
    assert str(duplicate_error.value) == "steward_refs must contain unique non-empty references"

    assert OwnershipMetadata(1, " group/data ", (" user/a ",)).steward_refs == ("user/a",)


def test_release_parser_preserves_prerelease_number_zero() -> None:
    assert parse_comparable_release("1.2rc").prerelease == (3, 0)
    assert parse_comparable_release("1.2rc2").prerelease == (3, 2)


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [("1.2", "1.10", -1), ("1.10", "1.2", 1), ("1.2", "1.2.0", 0)],
)
def test_release_comparison_preserves_strict_signed_order(
    left: str, right: str, expected: int
) -> None:
    assert compare_releases(left, right) == expected


def test_bind_policy_error_lists_the_exact_closed_vocabulary() -> None:
    assert tuple(BIND_POLICIES) == (
        "loopback",
        "container-internal",
        "insecure-plaintext-network",
    )
    with pytest.raises(ValueError, match=".") as error:
        parse_bind_policy("invalid")
    assert str(error.value) == (
        "RONIN_BIND_POLICY must be one of: loopback, container-internal, insecure-plaintext-network"
    )


def test_bind_policy_returns_each_supported_literal_and_default() -> None:
    assert parse_bind_policy(None) == "loopback"
    assert tuple(parse_bind_policy(value) for value in BIND_POLICIES) == BIND_POLICIES
