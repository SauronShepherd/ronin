"""Boundary matrices for canonical JSON, bundle paths, portability and quality pairs."""

from __future__ import annotations

import math

import pytest
from studio_core import (
    AssetId,
    AssetRef,
    AssetVersion,
    bundle_inventory,
    canonical_json,
    portability,
    quality,
)


@pytest.mark.parametrize("value", [None, True, "text", 1, -1, 1.5, [], {}, {"nested": [1, False]}])
def test_canonical_json_accepts_supported_values(value: object) -> None:
    encoded = canonical_json.encode(value)
    assert canonical_json.decode(encoded) == value


@pytest.mark.parametrize(
    "value", [2**53, -(2**53), math.inf, -math.inf, math.nan, object(), {1: "bad"}]
)
def test_canonical_json_rejects_unsafe_values(value: object) -> None:
    with pytest.raises((ValueError, TypeError)):
        canonical_json.encode(value)


def test_canonical_json_enforces_exact_boundaries_and_duplicate_members() -> None:
    assert canonical_json.encode({"z": 1, "a": 2}) == b'{"a":2,"z":1}'
    with pytest.raises(ValueError, match="duplicate canonical JSON object member"):
        canonical_json.decode('{"a":1,"a":2}')
    with pytest.raises(ValueError, match="non-finite canonical JSON number"):
        canonical_json.decode("NaN")
    with pytest.raises(ValueError, match="canonical JSON payload is invalid"):
        canonical_json.decode("not-json")


@pytest.mark.parametrize(
    "path",
    [
        "",
        ".",
        "..",
        "./file",
        "../file",
        "/absolute",
        "folder\\file",
        "folder//file",
        "ronin-inventory.json",
    ],
)
def test_bundle_inventory_safe_path_rejects_all_unsafe_forms(path: str) -> None:
    with pytest.raises(ValueError, match="."):
        bundle_inventory._require_safe_path(path)


@pytest.mark.parametrize("path", ["file.json", "folder/file.json", "folder/../file.json"])
def test_bundle_inventory_safe_path_accepts_only_relative_forward_slash_paths(path: str) -> None:
    if ".." in path:
        with pytest.raises(ValueError, match="unsafe components"):
            bundle_inventory._require_safe_path(path)
    else:
        assert bundle_inventory._require_safe_path(path) == path


@pytest.mark.parametrize(
    "path", ["", ".", "..", "./file", "../file", "/absolute", "folder\\file", "folder//file"]
)
def test_portability_safe_path_rejects_all_unsafe_forms(path: str) -> None:
    with pytest.raises(ValueError, match="."):
        portability._require_safe_path(path)


@pytest.mark.parametrize(
    "value", ["Bearer token", "-----BEGIN PRIVATE KEY-----", "password=secret"]
)
def test_portability_credential_material_is_rejected_case_insensitively(value: str) -> None:
    with pytest.raises(ValueError, match="credential material"):
        portability._reject_credential_material(value, "reference")


@pytest.mark.parametrize("value", ["bearerish", "private key", "passwordless"])
def test_portability_credential_near_misses_are_not_rejected(value: str) -> None:
    assert portability._reject_credential_material(value, "reference") == value


@pytest.mark.parametrize(
    "value", ["", " ", " leading", "trailing ", "line\nvalue", "line\rvalue", "nul\x00value"]
)
def test_quality_text_validator_rejects_noncanonical_values(value: str) -> None:
    with pytest.raises(ValueError, match="^field must be non-empty, trimmed, and single-line$"):
        quality._require_text(value, "field")


@pytest.mark.parametrize("term", ["password", "secret", "token", "credential", "api_key"])
def test_quality_pairs_reject_each_credential_key_marker(term: str) -> None:
    with pytest.raises(ValueError, match="credential-bearing keys"):
        quality._pairs(((f"prefix-{term.upper()}-suffix", "value"),), name="quality parameters")


def test_quality_pairs_canonicalize_and_reject_duplicate_keys() -> None:
    assert quality._pairs((("z", "last"), ("a", "first")), name="quality parameters") == (
        ("a", "first"),
        ("z", "last"),
    )
    with pytest.raises(ValueError, match="keys must be unique"):
        quality._pairs((("key", "one"), ("key", "two")), name="quality parameters")


@pytest.mark.parametrize("value", [None, [], [("key",)], [("key", "value", "extra")]])
def test_quality_pairs_reject_malformed_pair_shapes(value: object) -> None:
    with pytest.raises(ValueError, match="must contain key/value pairs"):
        quality._pairs(value, name="quality parameters")  # type: ignore[arg-type]


def test_quality_models_fail_closed_for_noncanonical_enum_and_scalar_types() -> None:
    rule_id = quality.QualityRuleId("rule")
    with pytest.raises(ValueError, match="unsupported quality rule kind"):
        quality.QualityRule(rule_id, [], "Rule")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="quality severity"):
        quality.QualityRule(rule_id, "null", "Rule", severity=[])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="quality blocking"):
        quality.QualityRule(rule_id, "null", "Rule", blocking=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unsupported schema compatibility"):
        quality.DataContract(
            AssetRef(AssetId("asset"), AssetVersion("1")),
            [],  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="unsupported quality status"):
        quality.QualityResult(rule_id, [])  # type: ignore[arg-type]
