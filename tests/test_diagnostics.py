import json
from pathlib import Path

import pytest
from studio_core import (
    DiagnosticCatalog,
    DiagnosticFact,
    DiagnosticFinding,
    DiagnosticPredicate,
    DiagnosticRule,
    builtin_diagnostic_catalog,
)


def _rule(
    rule_id: str = "test.rule",
    *,
    predicates: tuple[DiagnosticPredicate, ...] | None = None,
    severity: str = "error",
    checks: tuple[str, ...] = (),
    remediation: str | None = None,
    documentation_key: str | None = None,
) -> DiagnosticRule:
    actual_predicates = (
        predicates
        if predicates is not None
        else (DiagnosticPredicate("category", "equals", "test"),)
    )
    return DiagnosticRule(
        id=rule_id,
        title="Test rule",
        severity=severity,  # type: ignore[arg-type]
        predicates=actual_predicates,
        message="Test diagnostic message.",
        checks=checks,
        remediation=remediation,
        documentation_key=documentation_key,
    )


def test_diagnostic_predicate_rejects_invalid_metadata() -> None:
    with pytest.raises(ValueError, match="field"):
        DiagnosticPredicate("invalid", "equals", "value")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="match kind"):
        DiagnosticPredicate("category", "invalid", "value")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-empty"):
        DiagnosticPredicate("category", "equals", " ")
    with pytest.raises(ValueError, match="line breaks"):
        DiagnosticPredicate("message", "contains", "bad\nvalue")
    with pytest.raises(ValueError, match="at most 500"):
        DiagnosticPredicate("message", "contains", "x" * 501)


def test_diagnostic_rule_validates_and_canonicalizes_metadata() -> None:
    first = DiagnosticPredicate("message", "contains", "alpha")
    second = DiagnosticPredicate("code", "prefix", "E-")
    rule = _rule(
        predicates=(first, second),
        checks=("Second check.", "First check."),
        remediation="Repair the input.",
        documentation_key="diagnostic.test",
    )
    assert rule.predicates == tuple(sorted((first, second)))
    assert rule.checks == ("First check.", "Second check.")
    assert rule.to_data()["documentation_key"] == "diagnostic.test"

    for kwargs, match in (
        ({"rule_id": " "}, "rule id"),
        ({"severity": "fatal"}, "severity"),
        ({"predicates": ()}, "predicates must be non-empty"),
        ({"checks": (" ",)}, "diagnostic check"),
        ({"checks": ("same", "same")}, "checks must be unique"),
        ({"remediation": " "}, "remediation"),
        ({"documentation_key": " "}, "documentation key"),
    ):
        with pytest.raises(ValueError, match=match):
            _rule(**kwargs)  # type: ignore[arg-type]

    duplicate = DiagnosticPredicate("category", "equals", "test")
    with pytest.raises(ValueError, match="predicates must be unique"):
        _rule(predicates=(duplicate, duplicate))

    with pytest.raises(ValueError, match="rule title"):
        DiagnosticRule("id", " ", "error", (duplicate,), "Message")
    with pytest.raises(ValueError, match="rule message"):
        DiagnosticRule("id", "Title", "error", (duplicate,), " ")


def test_diagnostic_fact_is_bounded_and_requires_normalized_single_line_values() -> None:
    fact = DiagnosticFact("execution.failure", code="E-42", message="failed", source="runner")
    assert fact.code == "E-42"
    assert DiagnosticFact("execution.failure") == DiagnosticFact("execution.failure")
    with pytest.raises(ValueError, match="category"):
        DiagnosticFact(" ")
    with pytest.raises(ValueError, match="line breaks"):
        DiagnosticFact("execution.failure", message="line one\nline two")
    with pytest.raises(ValueError, match="at most 500"):
        DiagnosticFact("execution.failure", code="x" * 501)
    with pytest.raises(ValueError, match="at most 10000"):
        DiagnosticFact("execution.failure", message="x" * 10_001)
    with pytest.raises(ValueError, match="at most 500"):
        DiagnosticFact("execution.failure", source="x" * 501)


def test_catalog_is_canonical_unique_and_serializable() -> None:
    z_rule = _rule("z.rule")
    a_rule = _rule("a.rule")
    catalog = DiagnosticCatalog((z_rule, a_rule))
    assert [rule.id for rule in catalog.rules] == ["a.rule", "z.rule"]
    assert catalog.get("z.rule") == z_rule
    assert catalog.get("missing") is None
    assert json.loads(catalog.to_json()) == catalog.to_data()
    with pytest.raises(ValueError, match="ids must be unique"):
        DiagnosticCatalog((a_rule, a_rule))


def test_matcher_supports_bounded_non_regex_predicates_and_all_semantics() -> None:
    insensitive = _rule(
        "a.insensitive",
        predicates=(
            DiagnosticPredicate("category", "equals", "Execution.Failure"),
            DiagnosticPredicate("message", "contains", "quota"),
            DiagnosticPredicate("code", "prefix", "ERR-"),
            DiagnosticPredicate("source", "equals", "worker"),
        ),
        checks=("Inspect quota.",),
        remediation="Raise an approved quota.",
        documentation_key="diagnostic.quota",
    )
    sensitive = _rule(
        "b.sensitive",
        predicates=(DiagnosticPredicate("code", "equals", "ERR-42", case_sensitive=True),),
        severity="warning",
    )
    nonmatch = _rule(
        "c.nonmatch",
        predicates=(DiagnosticPredicate("message", "contains", "missing text"),),
    )
    fact = DiagnosticFact(
        "execution.failure",
        code="ERR-42",
        message="Resource QUOTA exceeded",
        source="WORKER",
    )
    findings = DiagnosticCatalog((nonmatch, sensitive, insensitive)).match(fact)
    assert [finding.rule_id for finding in findings] == ["a.insensitive", "b.sensitive"]
    assert findings[0].checks == ("Inspect quota.",)
    assert findings[0].remediation == "Raise an approved quota."
    assert findings[0].documentation_key == "diagnostic.quota"
    assert findings[0].to_data()["fact_code"] == "ERR-42"
    assert DiagnosticCatalog((sensitive,)).match(DiagnosticFact("x", code="err-42")) == ()


def test_matching_order_does_not_compare_optional_fields() -> None:
    first = _rule("same-a", documentation_key=None, remediation=None)
    second = _rule("same-b", documentation_key="docs", remediation="fix")
    findings = DiagnosticCatalog((second, first)).match(DiagnosticFact("test"))
    assert [finding.rule_id for finding in findings] == ["same-a", "same-b"]
    assert isinstance(findings[0], DiagnosticFinding)


def test_builtin_diagnostic_catalog_matches_golden_seed_and_is_portable() -> None:
    catalog = builtin_diagnostic_catalog()
    projection = [{"id": rule.id, "severity": rule.severity} for rule in catalog.rules]
    expected = json.loads(
        Path("tests/golden/diagnostic_seed_refs.json").read_text(encoding="utf-8")
    )
    assert projection == expected
    serialized = catalog.to_json().lower()
    assert "spark" not in serialized
    assert "databricks" not in serialized
    assert "fabric" not in serialized
    assert "kubernetes" not in serialized
    for rule in catalog.rules:
        finding = catalog.match(DiagnosticFact(rule.id))[0]
        assert finding.rule_id == rule.id
        assert finding.remediation
        assert finding.checks
        assert finding.documentation_key
