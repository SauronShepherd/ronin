"""Provider-neutral diagnostic contracts and deterministic fact matching."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, TypeAlias

DiagnosticSeverity: TypeAlias = Literal["info", "warning", "error"]
DiagnosticField: TypeAlias = Literal["category", "code", "message", "source"]
DiagnosticMatchKind: TypeAlias = Literal["equals", "contains", "prefix"]


def _require_text(value: str, field_name: str, *, max_length: int = 500) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    if "\n" in value or "\r" in value:
        raise ValueError(f"{field_name} must not contain line breaks")
    if len(value) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")


@dataclass(frozen=True, order=True, slots=True)
class DiagnosticPredicate:
    """Bounded matcher over normalized diagnostic facts; no regex or executable syntax."""

    field: DiagnosticField
    kind: DiagnosticMatchKind
    value: str
    case_sensitive: bool = False

    def __post_init__(self) -> None:
        if self.field not in {"category", "code", "message", "source"}:
            raise ValueError("unsupported diagnostic field")
        if self.kind not in {"equals", "contains", "prefix"}:
            raise ValueError("unsupported diagnostic match kind")
        _require_text(self.value, "diagnostic predicate value")


@dataclass(frozen=True, slots=True)
class DiagnosticRule:
    """Portable, immutable diagnostic rule over adapter-normalized evidence."""

    id: str
    title: str
    severity: DiagnosticSeverity
    predicates: tuple[DiagnosticPredicate, ...]
    message: str
    checks: tuple[str, ...] = ()
    remediation: str | None = None
    documentation_key: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.id, "diagnostic rule id")
        _require_text(self.title, "diagnostic rule title")
        _require_text(self.message, "diagnostic rule message")
        if self.severity not in {"info", "warning", "error"}:
            raise ValueError("unsupported diagnostic severity")
        if not self.predicates:
            raise ValueError("diagnostic rule predicates must be non-empty")
        canonical_predicates = tuple(sorted(self.predicates))
        if len(canonical_predicates) != len(set(canonical_predicates)):
            raise ValueError("diagnostic rule predicates must be unique")
        for check in self.checks:
            _require_text(check, "diagnostic check")
        canonical_checks = tuple(sorted(self.checks))
        if len(canonical_checks) != len(set(canonical_checks)):
            raise ValueError("diagnostic checks must be unique")
        if self.remediation is not None:
            _require_text(self.remediation, "diagnostic remediation")
        if self.documentation_key is not None:
            _require_text(self.documentation_key, "diagnostic documentation key")
        object.__setattr__(self, "predicates", canonical_predicates)
        object.__setattr__(self, "checks", canonical_checks)

    def to_data(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "severity": self.severity,
            "predicates": [
                {
                    "field": predicate.field,
                    "kind": predicate.kind,
                    "value": predicate.value,
                    "case_sensitive": predicate.case_sensitive,
                }
                for predicate in self.predicates
            ],
            "message": self.message,
            "checks": list(self.checks),
            "remediation": self.remediation,
            "documentation_key": self.documentation_key,
        }


@dataclass(frozen=True, order=True, slots=True)
class DiagnosticFact:
    """Normalized failure evidence emitted by adapters or pure validation layers."""

    category: str
    code: str = ""
    message: str = ""
    source: str = ""

    def __post_init__(self) -> None:
        _require_text(self.category, "diagnostic fact category")
        for value, field_name, limit in (
            (self.code, "diagnostic fact code", 500),
            (self.message, "diagnostic fact message", 10_000),
            (self.source, "diagnostic fact source", 500),
        ):
            if value:
                _require_text(value, field_name, max_length=limit)


@dataclass(frozen=True, order=True, slots=True)
class DiagnosticFinding:
    """Stable evidence produced when a rule matches one normalized fact."""

    rule_id: str
    severity: DiagnosticSeverity
    message: str
    fact_category: str
    fact_code: str = ""
    fact_source: str = ""
    documentation_key: str | None = None
    remediation: str | None = None
    checks: tuple[str, ...] = ()

    def to_data(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "fact_category": self.fact_category,
            "fact_code": self.fact_code,
            "fact_source": self.fact_source,
            "documentation_key": self.documentation_key,
            "remediation": self.remediation,
            "checks": list(self.checks),
        }


@dataclass(frozen=True, slots=True)
class DiagnosticCatalog:
    """Canonical diagnostic rule collection with deterministic matching."""

    rules: tuple[DiagnosticRule, ...] = ()

    def __post_init__(self) -> None:
        canonical = tuple(sorted(self.rules, key=lambda rule: rule.id))
        ids = [rule.id for rule in canonical]
        if len(ids) != len(set(ids)):
            raise ValueError("diagnostic rule ids must be unique within a catalog")
        object.__setattr__(self, "rules", canonical)

    def get(self, rule_id: str) -> DiagnosticRule | None:
        return next((rule for rule in self.rules if rule.id == rule_id), None)

    def match(self, fact: DiagnosticFact) -> tuple[DiagnosticFinding, ...]:
        findings = [
            DiagnosticFinding(
                rule_id=rule.id,
                severity=rule.severity,
                message=rule.message,
                fact_category=fact.category,
                fact_code=fact.code,
                fact_source=fact.source,
                documentation_key=rule.documentation_key,
                remediation=rule.remediation,
                checks=rule.checks,
            )
            for rule in self.rules
            if all(_matches(predicate, fact) for predicate in rule.predicates)
        ]
        return tuple(sorted(findings))

    def to_data(self) -> dict[str, object]:
        return {"rules": [rule.to_data() for rule in self.rules]}

    def to_json(self) -> str:
        return json.dumps(self.to_data(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def builtin_diagnostic_catalog() -> DiagnosticCatalog:
    """Portable seed adapted from mature SDP Studio failure categories."""
    return DiagnosticCatalog(
        (
            DiagnosticRule(
                id="schema.unresolved-field",
                title="Unresolved field",
                severity="error",
                predicates=(DiagnosticPredicate("category", "equals", "schema.unresolved-field"),),
                message="A referenced field cannot be resolved from the available schema.",
                checks=("Compare the expression with the upstream schema.",),
                remediation="Check spelling, aliases, and upstream schema changes.",
                documentation_key="diagnostic.schema.unresolved-field",
            ),
            DiagnosticRule(
                id="schema.type-mismatch",
                title="Type mismatch",
                severity="error",
                predicates=(DiagnosticPredicate("category", "equals", "schema.type-mismatch"),),
                message="An expression or operation received incompatible data types.",
                checks=("Compare operand types with the operator contract and input schema.",),
                remediation="Cast values explicitly or choose a type-compatible operator.",
                documentation_key="diagnostic.schema.type-mismatch",
            ),
            DiagnosticRule(
                id="execution.resource-exhausted",
                title="Resource exhausted",
                severity="error",
                predicates=(
                    DiagnosticPredicate("category", "equals", "execution.resource-exhausted"),
                ),
                message="Execution exhausted an assigned compute or memory resource.",
                checks=("Inspect partitioning, skew, concurrency, and configured resource limits.",),
                remediation="Reduce resource pressure or select an approved profile with more capacity.",
                documentation_key="diagnostic.execution.resource-exhausted",
            ),
            DiagnosticRule(
                id="execution.capability-unsupported",
                title="Unsupported capability",
                severity="error",
                predicates=(
                    DiagnosticPredicate("category", "equals", "execution.capability-unsupported"),
                ),
                message="The selected runtime cannot satisfy the requested execution capability.",
                checks=("Compare the request with the resolved runtime capability evidence.",),
                remediation="Choose a compatible runtime profile or adjust the requested capability.",
                documentation_key="diagnostic.execution.capability-unsupported",
            ),
            DiagnosticRule(
                id="execution.mode-mismatch",
                title="Execution mode mismatch",
                severity="error",
                predicates=(DiagnosticPredicate("category", "equals", "execution.mode-mismatch"),),
                message="A batch and streaming boundary is incompatible.",
                checks=("Verify source mode and downstream operator contracts.",),
                remediation="Use compatible operators or materialize the boundary.",
                documentation_key="diagnostic.execution.mode-mismatch",
            ),
            DiagnosticRule(
                id="dependency.missing",
                title="Missing dependency",
                severity="error",
                predicates=(DiagnosticPredicate("category", "equals", "dependency.missing"),),
                message="A required runtime dependency is unavailable.",
                checks=("Verify the resolved runtime dependency inventory and required versions.",),
                remediation="Install an approved dependency or select a runtime profile that provides it.",
                documentation_key="diagnostic.dependency.missing",
            ),
            DiagnosticRule(
                id="access.denied",
                title="Access denied",
                severity="error",
                predicates=(DiagnosticPredicate("category", "equals", "access.denied"),),
                message="Execution was denied access to a required resource.",
                checks=("Inspect the effective identity and least-privilege authorization evidence.",),
                remediation="Grant only the required permission or correct the resource binding.",
                documentation_key="diagnostic.access.denied",
            ),
            DiagnosticRule(
                id="state.mutation-detected",
                title="Shared state mutation",
                severity="warning",
                predicates=(DiagnosticPredicate("category", "equals", "state.mutation-detected"),),
                message="Execution attempted to mutate shared runtime state.",
                checks=("Locate mutable runtime configuration changes in user-owned code.",),
                remediation="Move configuration into the runtime profile or an approved isolated boundary.",
                documentation_key="diagnostic.state.mutation-detected",
            ),
        )
    )


def _matches(predicate: DiagnosticPredicate, fact: DiagnosticFact) -> bool:
    actual = getattr(fact, predicate.field)
    expected = predicate.value
    if not predicate.case_sensitive:
        actual = actual.casefold()
        expected = expected.casefold()
    if predicate.kind == "equals":
        return actual == expected
    if predicate.kind == "contains":
        return expected in actual
    return actual.startswith(expected)
