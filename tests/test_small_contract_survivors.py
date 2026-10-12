"""Boundary contracts for small, high-fanout validators.

These tests exercise the product's observable fail-closed behavior directly;
they are intentionally independent of mutation-tool output.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from studio_core import audit, genai, ml, scheduler, source_control


@pytest.mark.parametrize("validator", [audit._require_text, scheduler._require_text])
@pytest.mark.parametrize(
    "value", ["", " value", "value ", "line\nfeed", "line\rfeed", "value\x00tail"]
)
def test_audit_and_scheduler_text_contracts_reject_all_noncanonical_shapes(
    validator, value: str
) -> None:
    with pytest.raises(ValueError, match=r"must be non-empty, trimmed, and single-line"):
        validator(value, "field")


@pytest.mark.parametrize("validator", [genai._text, ml._text])
@pytest.mark.parametrize(
    "value", ["", " value", "value ", "line\nfeed", "line\rfeed", "value\x00tail"]
)
def test_genai_and_ml_text_contracts_reject_all_noncanonical_shapes(validator, value: str) -> None:
    with pytest.raises(ValueError, match=r"must be non-empty, trimmed, and single-line"):
        validator(value, "field")


@pytest.mark.parametrize("validator", [genai._text, ml._text])
def test_provider_text_contracts_reject_non_strings(validator) -> None:
    with pytest.raises(ValueError, match=r"^field must be non-empty, trimmed, and single-line$"):
        validator(123, "field")  # type: ignore[arg-type]


@pytest.mark.parametrize("validator", [genai._pairs, ml._pairs])
def test_provider_pairs_are_sorted_and_reject_invalid_keys_values_and_duplicates(validator) -> None:
    assert validator((("z", "last"), ("a", "first")), "properties") == (
        ("a", "first"),
        ("z", "last"),
    )
    with pytest.raises(ValueError, match=r"^properties key must be non-empty"):
        validator((("", "value"),), "properties")
    with pytest.raises(ValueError, match=r"^properties value must be non-empty"):
        validator((("key", ""),), "properties")
    with pytest.raises(ValueError, match=r"^properties keys must be unique$"):
        validator((("key", "one"), ("key", "two")), "properties")


@pytest.mark.parametrize("term", ["password", "secret", "token", "credential", "api_key"])
@pytest.mark.parametrize("validator", [genai._pairs, ml._pairs])
def test_provider_pairs_reject_each_credential_key_marker(validator, term: str) -> None:
    with pytest.raises(ValueError, match=r"^properties must not contain credential-bearing keys$"):
        validator(((f"prefix-{term.upper()}-suffix", "redacted"),), "properties")


@pytest.mark.parametrize("term", ["password", "secret", "token", "credential", "api_key"])
def test_audit_metadata_rejects_each_credential_key_marker(term: str) -> None:
    with pytest.raises(
        ValueError, match=r"^audit metadata must not contain credential-bearing keys$"
    ):
        audit._metadata(((f"prefix-{term.upper()}-suffix", "redacted"),))


def test_audit_metadata_rejects_invalid_pairs_and_canonicalizes_valid_pairs() -> None:
    assert audit._metadata((("z", "last"), ("a", "first"))) == (
        ("a", "first"),
        ("z", "last"),
    )
    with pytest.raises(ValueError, match=r"^audit metadata key must be non-empty"):
        audit._metadata((("", "value"),))
    with pytest.raises(ValueError, match=r"^audit metadata value must be non-empty"):
        audit._metadata((("key", ""),))
    with pytest.raises(ValueError, match=r"^audit metadata keys must be unique$"):
        audit._metadata((("key", "one"), ("key", "two")))


def test_source_text_rejects_nul_and_safe_checkout_rejects_symlink_components(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match=r"^source field must be non-empty and single-line$"):
        source_control._text("value\x00tail", "source field")

    root = tmp_path / "worktree"
    root.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    link = root / "linked"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available in this environment")
    with pytest.raises(ValueError, match=r"^checkout subdirectory must not traverse a symlink$"):
        source_control.safe_checkout_path(root, "linked/child")
