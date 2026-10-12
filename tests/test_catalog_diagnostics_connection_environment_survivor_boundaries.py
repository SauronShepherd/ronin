"""Focused boundary contracts for the remaining low-cardinality survivors."""

from __future__ import annotations

import pytest
from studio_core import catalog, connections, diagnostics, environments
from studio_core.diagnostics import (
    DiagnosticFact,
    DiagnosticFinding,
    DiagnosticPredicate,
)


@pytest.mark.parametrize(
    "value", ["", " ", " leading", "trailing ", "line\nvalue", "line\rvalue", "nul\x00value"]
)
def test_catalog_require_text_rejects_every_noncanonical_shape(value: str) -> None:
    with pytest.raises(ValueError, match=r"^field must be non-empty, trimmed, and single-line$"):
        catalog._require_text(value, "field")


def test_catalog_canonical_pairs_validate_context_sensitive_keys_and_values() -> None:
    assert catalog._canonical_pairs((("z", "last"), ("a", "first")), name="properties") == (
        ("a", "first"),
        ("z", "last"),
    )
    with pytest.raises(
        ValueError, match=r"^properties key must be non-empty, trimmed, and single-line$"
    ):
        catalog._canonical_pairs((("", "value"),), name="properties")
    with pytest.raises(
        ValueError, match=r"^properties value must be non-empty, trimmed, and single-line$"
    ):
        catalog._canonical_pairs((("key", ""),), name="properties")
    with pytest.raises(ValueError, match=r"^properties keys must be unique$"):
        catalog._canonical_pairs((("key", "one"), ("key", "two")), name="properties")


@pytest.mark.parametrize(
    "term",
    [
        "password",
        "secret",
        "token",
        "credential",
        "api_key",
        "api-key",
        "access_key",
        "access-key",
        "private_key",
        "private-key",
    ],
)
def test_catalog_canonical_pairs_reject_each_sensitive_key_marker(term: str) -> None:
    with pytest.raises(ValueError, match=r"^properties must not contain credential-bearing keys$"):
        catalog._canonical_pairs(
            ((f"prefix-{term.upper()}-suffix", "redacted"),),
            name="properties",
            reject_sensitive=True,
        )


@pytest.mark.parametrize(
    "value", ["", " ", " leading", "trailing ", "line\nvalue", "line\rvalue", "nul\x00value"]
)
def test_connection_and_environment_text_validators_reject_every_noncanonical_shape(
    value: str,
) -> None:
    for validator in (connections._require_text, environments._require_text):
        with pytest.raises(
            ValueError, match=r"^field must be non-empty, trimmed, and single-line$"
        ):
            validator(value, "field")


@pytest.mark.parametrize(
    "term",
    [
        "password",
        "secret",
        "token",
        "credential",
        "api_key",
        "api-key",
        "access_key",
        "access-key",
        "private_key",
        "private-key",
    ],
)
def test_connection_safe_option_key_rejects_each_sensitive_marker(term: str) -> None:
    with pytest.raises(
        ValueError, match=r"^secret-bearing connection settings must use secret_refs$"
    ):
        connections._require_safe_option_key(f"prefix-{term.upper()}-suffix")
    assert connections._require_safe_option_key("region") == "region"


@pytest.mark.parametrize(
    "term",
    [
        "password=",
        "token=",
        "secret=",
        "api_key=",
        "api-key=",
        "access_key=",
        "access-key=",
        "private_key=",
        "private-key=",
        "bearer ",
        "-----begin ",
    ],
)
def test_environment_safe_ref_rejects_each_credential_marker(term: str) -> None:
    with pytest.raises(
        ValueError, match=r"^binding source_ref must not contain credential material$"
    ):
        environments._safe_ref(f"prefix-{term.upper()}opaque", "binding source_ref")
    assert (
        environments._safe_ref("runtime://worker-a", "binding source_ref") == "runtime://worker-a"
    )


@pytest.mark.parametrize("kind", ["equals", "contains", "prefix"])
@pytest.mark.parametrize("case_sensitive", [False, True])
def test_diagnostic_matches_enforces_exact_kind_semantics(kind: str, case_sensitive: bool) -> None:
    predicate = DiagnosticPredicate("message", kind, "Error", case_sensitive=case_sensitive)  # type: ignore[arg-type]
    exact = DiagnosticFact("category", message="Error")
    embedded = DiagnosticFact("category", message="preErrorpost")
    different_case = DiagnosticFact("category", message="error")
    if kind == "equals":
        assert diagnostics._matches(predicate, exact) is True
        assert diagnostics._matches(predicate, embedded) is False
    elif kind == "contains":
        assert diagnostics._matches(predicate, embedded) is True
        assert (
            diagnostics._matches(predicate, DiagnosticFact("category", message="prefix")) is False
        )
    else:
        assert (
            diagnostics._matches(predicate, DiagnosticFact("category", message="Error details"))
            is True
        )
        assert diagnostics._matches(predicate, embedded) is False
    assert diagnostics._matches(predicate, different_case) is (not case_sensitive)


def test_diagnostic_finding_sort_key_uses_empty_defaults_for_optional_fields() -> None:
    no_optional = DiagnosticFinding("rule", "warning", "message", "category")
    with_optional = DiagnosticFinding(
        "rule", "warning", "message", "category", documentation_key="docs", remediation="fix"
    )
    assert diagnostics._finding_sort_key(no_optional) == (
        "rule",
        "warning",
        "message",
        "category",
        "",
        "",
        "",
        "",
    )
    assert diagnostics._finding_sort_key(with_optional) == (
        "rule",
        "warning",
        "message",
        "category",
        "",
        "",
        "docs",
        "fix",
    )
