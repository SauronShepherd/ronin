from __future__ import annotations

import pytest
from studio_core import (
    canonical_json,
    connections,
    diagnostics,
    environments,
    quality,
    reproducible_manifest,
    runtime_profiles,
    scheduler_events,
    scheduler_resources,
)


@pytest.mark.parametrize(
    "validator",
    [
        connections._require_text,
        environments._require_text,
        scheduler_events._require_text,
        diagnostics._require_text,
    ],
)
@pytest.mark.parametrize("value", [123, "value\x00tail", " value", "value\nnext"])
def test_shared_boundary_text_validators_fail_closed(validator, value: object) -> None:
    with pytest.raises(ValueError, match="."):
        validator(value, "field")  # type: ignore[arg-type]


def test_scheduler_pool_name_validator_rejects_noncanonical_values() -> None:
    for value in (123, "value\x00tail", " value", "value\rnext"):
        with pytest.raises(ValueError, match="resource pool name"):
            scheduler_resources._require_pool_name(value)  # type: ignore[arg-type]


def test_reproducible_manifest_text_map_sorts_and_validates_keys_and_values() -> None:
    assert reproducible_manifest._text_map(
        {"z": "last", "a": "first"}, "configuration"
    ) == (("a", "first"), ("z", "last"))
    with pytest.raises(ValueError, match="configuration key"):
        reproducible_manifest._text_map({"": "value"}, "configuration")
    with pytest.raises(ValueError, match="configuration.bad"):
        reproducible_manifest._text_map({"bad": "value\x00tail"}, "configuration")
    with pytest.raises(TypeError, match="object with string keys"):
        reproducible_manifest._mapping({1: "value"}, "configuration")


def test_canonical_json_boundary_accepts_all_exact_numeric_edges() -> None:
    assert canonical_json.encode(-(2**53 - 1)) == b"-9007199254740991"
    assert canonical_json.encode(-0.0) == b"-0.0"
    assert canonical_json.decode(b"[1,2.5,false,null,\"text\"]") == [
        1,
        2.5,
        False,
        None,
        "text",
    ]


def test_diagnostic_matcher_has_distinct_equals_contains_and_prefix_semantics() -> None:
    fact = diagnostics.DiagnosticFact("category", message="Error: quota exceeded")
    assert diagnostics._matches(
        diagnostics.DiagnosticPredicate("message", "equals", "error: quota exceeded"),
        fact,
    )
    assert diagnostics._matches(
        diagnostics.DiagnosticPredicate("message", "contains", "quota"), fact
    )
    assert diagnostics._matches(
        diagnostics.DiagnosticPredicate("message", "prefix", "error:"), fact
    )
    assert not diagnostics._matches(
        diagnostics.DiagnosticPredicate("message", "equals", "quota"), fact
    )


@pytest.mark.parametrize("validator", [quality._require_text, runtime_profiles._require_text])
@pytest.mark.parametrize("value", [123, "value\x00tail", " value", "value\nnext"])
def test_quality_and_runtime_text_validators_fail_closed(validator, value: object) -> None:
    with pytest.raises(ValueError, match="."):
        validator(value, "field")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "constraint", "expected"),
    [
        ("3.12", ">=3.11", True),
        ("3.10", ">=3.11", False),
        ("3.11", "<=3.11", True),
        ("3.12", "<3.11", False),
        ("stable", "==stable", True),
        ("stable", "!=preview", True),
        ("opaque", "opaque", True),
        ("vendor-build", ">=3.11", False),
    ],
)
def test_runtime_constraint_matching_preserves_each_operator_boundary(
    value: str, constraint: str, expected: bool
) -> None:
    assert runtime_profiles._matches_constraint(value, constraint)[0] is expected
