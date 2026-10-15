"""Directed tests for runtime resolution and bundle portability boundaries."""

from __future__ import annotations

import pytest
from studio_core import bundle_inventory, portability
from studio_core.runtime_profiles import (
    _matches_constraint,
    _matches_term,
)


@pytest.mark.parametrize("operator", [">=", "<=", "==", "!=", ">", "<"])
def test_runtime_constraint_operators_cover_equal_and_unequal_release_values(operator: str) -> None:
    expected = {
        ">=": True,
        "<=": True,
        "==": True,
        "!=": False,
        ">": False,
        "<": False,
    }[operator]
    assert _matches_term("4.0", f"{operator}4.0") is expected


def test_runtime_constraint_terms_support_plain_values_and_noncomparable_ordered_values() -> None:
    assert _matches_term("alpha", "alpha") is True
    assert _matches_term("alpha", "beta") is False
    assert _matches_term("latest", ">=4") is None
    assert _matches_constraint("4.0", ">=4, <5") == (True, "constraint satisfied")
    assert _matches_constraint("latest", ">=4") == (
        False,
        "ordered constraint requires comparable advertised release",
    )


@pytest.mark.parametrize("constraint", ["", " , ", "==4, !=4", ">4, <4"])
def test_runtime_constraint_combinations_fail_closed_when_not_satisfied(constraint: str) -> None:
    satisfied, reason = _matches_constraint("4", constraint)
    if constraint == "":
        assert satisfied is False or reason == "constraint not satisfied"
    else:
        assert satisfied is False
        assert reason in {
            "constraint not satisfied",
            "ordered constraint requires comparable advertised release",
        }


@pytest.mark.parametrize(
    "value", ["", " ", " leading", "trailing ", "line\nvalue", "line\rvalue", "nul\x00value"]
)
def test_bundle_and_portability_text_contracts_reject_each_noncanonical_shape(value: str) -> None:
    for validator, name in (
        (bundle_inventory._require_text, "bundle field"),
        (portability._require_text, "bundle field"),
    ):
        with pytest.raises(ValueError, match="non-empty, trimmed, and single-line"):
            validator(value, name)


@pytest.mark.parametrize("value", [None, 0, [], {}])
def test_bundle_and_portability_text_contracts_fail_closed_for_non_strings(value: object) -> None:
    for validator, name in (
        (bundle_inventory._require_text, "bundle field"),
        (portability._require_text, "bundle field"),
    ):
        with pytest.raises(
            ValueError,
            match="^bundle field must be non-empty, trimmed, and single-line$",
        ):
            validator(value, name)  # type: ignore[arg-type]


@pytest.mark.parametrize("path", ["", " ", ".", "..", "a//b", "a/./b", "a/../b", "/a", "a\\b"])
def test_bundle_and_portability_paths_reject_empty_absolute_and_traversal_components(
    path: str,
) -> None:
    for validator in (bundle_inventory._require_safe_path, portability._require_safe_path):
        with pytest.raises(ValueError, match="."):
            validator(path)


def test_bundle_inventory_path_rejects_reserved_inventory_name_but_portability_allows_it() -> None:
    with pytest.raises(ValueError, match="must not reuse"):
        bundle_inventory._require_safe_path("ronin-inventory.json")
    assert portability._require_safe_path("ronin-inventory.json") == "ronin-inventory.json"


@pytest.mark.parametrize(
    "value", ["Bearer opaque", "-----BEGIN PRIVATE KEY-----", "password=secret"]
)
def test_portability_rejects_each_credential_material_marker(value: str) -> None:
    with pytest.raises(ValueError, match="must not contain credential material"):
        portability._reject_credential_material(value, "binding")


def test_portability_credential_filter_is_case_insensitive_and_preserves_safe_values() -> None:
    assert (
        portability._reject_credential_material("PUBLIC-REFERENCE", "binding") == "PUBLIC-REFERENCE"
    )
    with pytest.raises(ValueError, match="credential material"):
        portability._reject_credential_material("PASSWORD=secret", "binding")
