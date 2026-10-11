"""Adversarial contract coverage for the small validators shared by core models."""

from __future__ import annotations

import pytest
from studio_core import (
    audit,
    bundle_inventory,
    catalog,
    connections,
    grants,
    ml,
    ontology,
    operators,
    portability,
    project_manifest,
    quality,
    source_control,
)


@pytest.mark.parametrize(
    ("validator", "args"),
    [
        (ontology._require_text, ("", "field")),
        (grants._require_text, ("", "field")),
        (quality._require_text, ("", "field")),
        (ml._text, ("", "field")),
        (operators._require_text, ("", "field")),
        (portability._require_text, ("", "field")),
        (bundle_inventory._require_text, ("", "field")),
        (source_control._text, ("", "field")),
    ],
)
def test_core_text_validators_reject_empty_values(validator, args) -> None:
    with pytest.raises((TypeError, ValueError, AttributeError)):
        validator(*args)


@pytest.mark.parametrize(
    ("validator", "args"),
    [
        (ontology._require_text, (123, "field")),
        (grants._require_text, (123, "field")),
        (quality._require_text, (123, "field")),
        (ml._text, (123, "field")),
        (operators._require_text, (123, "field")),
        (portability._require_text, (123, "field")),
        (bundle_inventory._require_text, (123, "field")),
        (source_control._text, (123, "field")),
        (project_manifest._require_str, (123, "field")),
    ],
)
def test_core_text_validators_reject_non_strings(validator, args) -> None:
    with pytest.raises((TypeError, ValueError, AttributeError)):
        validator(*args)


@pytest.mark.parametrize(
    ("validator", "value"),
    [
        (ontology._require_text, " value"),
        (ontology._require_text, "value "),
        (ontology._require_text, "value\nother"),
        (grants._require_text, " value"),
        (grants._require_text, "value\nother"),
        (quality._require_text, " value"),
        (ml._text, "value\rother"),
        (portability._require_text, " value"),
        (bundle_inventory._require_text, "value\nother"),
        (source_control._text, "value\rother"),
        (catalog._require_text, " value"),
        (connections._require_text, "value\nother"),
        (audit._require_text, " value"),
    ],
)
def test_core_text_validators_reject_untrimmed_or_multiline_values(validator, value) -> None:
    with pytest.raises((TypeError, ValueError, AttributeError)):
        validator(value, "field")


def test_grants_text_validator_enforces_its_length_limit() -> None:
    with pytest.raises(ValueError, match="at most 256 characters"):
        grants._require_text("x" * 257, "field")


@pytest.mark.parametrize("value", ["../secret", "/absolute", "a/../../b", ""])
def test_safe_path_validators_reject_traversal_absolute_and_empty_paths(value: str) -> None:
    with pytest.raises((TypeError, ValueError)):
        portability._require_safe_path(value)
    with pytest.raises((TypeError, ValueError)):
        bundle_inventory._require_safe_path(value)


def test_pair_validators_reject_duplicate_keys_and_empty_text() -> None:
    with pytest.raises((TypeError, ValueError)):
        quality._pairs((("a", "1"), ("a", "2")), name="pairs")
    with pytest.raises((TypeError, ValueError)):
        ml._pairs((("", "1"),), "pairs")
