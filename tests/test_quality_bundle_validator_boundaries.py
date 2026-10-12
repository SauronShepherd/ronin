from __future__ import annotations

import pytest
from studio_core import bundle_inventory, quality


@pytest.mark.parametrize("value", ["line\nfeed", "carriage\rreturn", "nul\x00byte"])
def test_quality_text_validator_rejects_each_control_character(value: str) -> None:
    with pytest.raises(ValueError, match=".") as error:
        quality._require_text(value, "quality field")
    assert str(error.value) == "quality field must be non-empty, trimmed, and single-line"


@pytest.mark.parametrize("value", ["line\nfeed", "carriage\rreturn", "nul\x00byte"])
def test_bundle_text_validator_rejects_each_control_character(value: str) -> None:
    with pytest.raises(ValueError, match=".") as error:
        bundle_inventory._require_text(value, "bundle field")
    assert str(error.value) == "bundle field must be non-empty, trimmed, and single-line"


@pytest.mark.parametrize("marker", ["password", "secret", "token", "credential", "api_key"])
def test_quality_pairs_reject_each_sensitive_marker_in_a_mixed_case_key(marker: str) -> None:
    key = f"prefix-{marker.upper()}-suffix"
    with pytest.raises(ValueError, match=".") as error:
        quality._pairs(((key, "redacted"),), name="observed values")
    assert str(error.value) == "observed values must not contain credential-bearing keys"


def test_quality_pairs_validate_key_and_value_with_contextual_names() -> None:
    with pytest.raises(ValueError, match=".") as key_error:
        quality._pairs((("bad\nkey", "value"),), name="parameters")
    assert str(key_error.value) == "parameters key must be non-empty, trimmed, and single-line"

    with pytest.raises(ValueError, match=".") as value_error:
        quality._pairs((("key", "bad\rvalue"),), name="parameters")
    assert str(value_error.value) == "parameters value must be non-empty, trimmed, and single-line"


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("/objects/project.json", "bundle inventory path must be relative and use forward slashes"),
        ("objects\\project.json", "bundle inventory path must be relative and use forward slashes"),
        ("objects//project.json", "bundle inventory path contains unsafe components"),
        ("objects/./project.json", "bundle inventory path contains unsafe components"),
        ("objects/../project.json", "bundle inventory path contains unsafe components"),
        ("ronin-inventory.json", "bundle object path must not reuse the inventory path"),
    ],
)
def test_bundle_safe_path_reports_the_exact_rejection_reason(path: str, message: str) -> None:
    with pytest.raises(ValueError, match=".") as error:
        bundle_inventory._require_safe_path(path)
    assert str(error.value) == message


def test_bundle_safe_path_accepts_nested_forward_slash_paths() -> None:
    assert bundle_inventory._require_safe_path("objects/project/payload.json") == (
        "objects/project/payload.json"
    )
