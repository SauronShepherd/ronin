"""Provider-neutral data-contract and quality-result contracts for Public v1."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from .canonical_json import decode as decode_canonical_json
from .canonical_json import encode as encode_canonical_json
from .catalog import AssetRef

QualityRuleKind: TypeAlias = Literal[
    "null",
    "unique",
    "range",
    "domain",
    "row_count",
    "referential",
    "freshness",
    "custom_sql",
    "custom_python",
]
QualitySeverity: TypeAlias = Literal["info", "warning", "error"]
QualityStatus: TypeAlias = Literal["passed", "failed", "error", "unknown"]
SchemaCompatibility: TypeAlias = Literal["exact", "backward", "forward", "full"]

QUALITY_RULE_KINDS: frozenset[str] = frozenset(
    {
        "null",
        "unique",
        "range",
        "domain",
        "row_count",
        "referential",
        "freshness",
        "custom_sql",
        "custom_python",
    }
)


def _require_text(value: str, name: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    return value


def _pairs(values: tuple[tuple[str, str], ...], *, name: str) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key, value in values:
        key = _require_text(key, f"{name} key")
        value = _require_text(value, f"{name} value")
        folded = key.casefold()
        if any(term in folded for term in ("password", "secret", "token", "credential", "api_key")):
            raise ValueError(f"{name} must not contain credential-bearing keys")
        if key in seen:
            raise ValueError(f"{name} keys must be unique")
        seen.add(key)
        result.append((key, value))
    return tuple(sorted(result))


@dataclass(frozen=True, order=True, slots=True)
class QualityRuleId:
    value: str

    def __post_init__(self) -> None:
        _require_text(self.value, "quality rule id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class QualityRule:
    id: QualityRuleId
    kind: QualityRuleKind
    name: str
    severity: QualitySeverity = "error"
    blocking: bool = False
    field: str | None = None
    parameters: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in QUALITY_RULE_KINDS:
            raise ValueError("unsupported quality rule kind")
        _require_text(self.name, "quality rule name")
        if self.severity not in {"info", "warning", "error"}:
            raise ValueError("quality severity must be info, warning, or error")
        if self.field is not None:
            _require_text(self.field, "quality rule field")
        object.__setattr__(self, "parameters", _pairs(self.parameters, name="quality parameters"))

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id.value,
            "kind": self.kind,
            "name": self.name,
            "severity": self.severity,
            "blocking": self.blocking,
            "field": self.field,
            "parameters": dict(self.parameters),
        }

    @classmethod
    def from_payload(cls, payload: object) -> QualityRule:
        expected = {"id", "kind", "name", "severity", "blocking", "field", "parameters"}
        if not isinstance(payload, Mapping) or set(payload) != expected:
            raise ValueError("quality rule has invalid shape")
        identifier = payload["id"]
        kind = payload["kind"]
        name = payload["name"]
        severity = payload["severity"]
        blocking = payload["blocking"]
        field = payload["field"]
        parameters = payload["parameters"]
        if not isinstance(identifier, str) or not isinstance(kind, str) or not isinstance(name, str):
            raise ValueError("quality rule id, kind, and name must be strings")
        if not isinstance(severity, str) or severity not in {"info", "warning", "error"}:
            raise ValueError("invalid quality severity")
        if not isinstance(blocking, bool):
            raise ValueError("quality blocking must be boolean")
        if field is not None and not isinstance(field, str):
            raise ValueError("quality field must be string or null")
        if not isinstance(parameters, Mapping) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in parameters.items()
        ):
            raise ValueError("quality parameters must be string object")
        if kind not in QUALITY_RULE_KINDS:
            raise ValueError("unsupported quality rule kind")
        return cls(
            QualityRuleId(identifier),
            cast(QualityRuleKind, kind),
            name,
            cast(QualitySeverity, severity),
            blocking,
            cast(str | None, field),
            tuple(sorted(cast(Mapping[str, str], parameters).items())),
        )


@dataclass(frozen=True, slots=True)
class DataContract:
    """Versioned expectations attached to a committed governed asset revision."""

    asset: AssetRef
    compatibility: SchemaCompatibility
    rules: tuple[QualityRule, ...] = ()
    freshness_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.compatibility not in {"exact", "backward", "forward", "full"}:
            raise ValueError("unsupported schema compatibility mode")
        if self.freshness_seconds is not None and self.freshness_seconds < 1:
            raise ValueError("freshness_seconds must be positive")
        rules = tuple(sorted(self.rules, key=lambda rule: rule.id.value))
        identifiers = [rule.id for rule in rules]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("quality rule ids must be unique within a data contract")
        object.__setattr__(self, "rules", rules)

    def to_payload(self) -> dict[str, object]:
        return {
            "asset": self.asset.to_payload(),
            "compatibility": self.compatibility,
            "freshness_seconds": self.freshness_seconds,
            "rules": [rule.to_payload() for rule in self.rules],
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> DataContract:
        if not isinstance(payload, Mapping) or set(payload) != {
            "asset",
            "compatibility",
            "freshness_seconds",
            "rules",
        }:
            raise ValueError("data contract has invalid shape")
        compatibility = payload["compatibility"]
        freshness = payload["freshness_seconds"]
        rules = payload["rules"]
        if not isinstance(compatibility, str) or compatibility not in {
            "exact",
            "backward",
            "forward",
            "full",
        }:
            raise ValueError("unsupported schema compatibility mode")
        if freshness is not None and (not isinstance(freshness, int) or isinstance(freshness, bool)):
            raise ValueError("freshness_seconds must be integer or null")
        if not isinstance(rules, list):
            raise ValueError("data contract rules must be an array")
        return cls(
            asset=AssetRef.from_payload(payload["asset"]),
            compatibility=cast(SchemaCompatibility, compatibility),
            rules=tuple(QualityRule.from_payload(rule) for rule in rules),
            freshness_seconds=cast(int | None, freshness),
        )

    @classmethod
    def from_json(cls, payload: str) -> DataContract:
        return cls.from_payload(decode_canonical_json(payload))


@dataclass(frozen=True, order=True, slots=True)
class QualityRunId:
    value: str

    def __post_init__(self) -> None:
        _require_text(self.value, "quality run id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class QualityResult:
    rule_id: QualityRuleId
    status: QualityStatus
    observed: tuple[tuple[str, str], ...] = ()
    message: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"passed", "failed", "error", "unknown"}:
            raise ValueError("unsupported quality status")
        if self.message is not None:
            _require_text(self.message, "quality result message")
        object.__setattr__(self, "observed", _pairs(self.observed, name="quality observed values"))

    def to_payload(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id.value,
            "status": self.status,
            "observed": dict(self.observed),
            "message": self.message,
        }

    @classmethod
    def from_payload(cls, payload: object) -> QualityResult:
        if not isinstance(payload, Mapping) or set(payload) != {
            "rule_id",
            "status",
            "observed",
            "message",
        }:
            raise ValueError("quality result has invalid shape")
        rule_id = payload["rule_id"]
        status = payload["status"]
        observed = payload["observed"]
        message = payload["message"]
        if not isinstance(rule_id, str) or not isinstance(status, str) or status not in {
            "passed",
            "failed",
            "error",
            "unknown",
        }:
            raise ValueError("quality result has invalid identity/status")
        if message is not None and not isinstance(message, str):
            raise ValueError("quality result message must be string or null")
        if not isinstance(observed, Mapping) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in observed.items()
        ):
            raise ValueError("quality observed values must be string object")
        return cls(
            QualityRuleId(rule_id),
            cast(QualityStatus, status),
            tuple(sorted(cast(Mapping[str, str], observed).items())),
            cast(str | None, message),
        )


@dataclass(frozen=True, slots=True)
class QualityRun:
    id: QualityRunId
    asset: AssetRef
    execution_ref: str | None
    results: tuple[QualityResult, ...]

    def __post_init__(self) -> None:
        if self.execution_ref is not None:
            _require_text(self.execution_ref, "quality execution ref")
        results = tuple(sorted(self.results, key=lambda result: result.rule_id.value))
        identifiers = [result.rule_id for result in results]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("quality results must have unique rule ids")
        object.__setattr__(self, "results", results)

    @property
    def status(self) -> QualityStatus:
        states = {result.status for result in self.results}
        if "error" in states:
            return "error"
        if "failed" in states:
            return "failed"
        if "unknown" in states or not states:
            return "unknown"
        return "passed"

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id.value,
            "asset": self.asset.to_payload(),
            "execution_ref": self.execution_ref,
            "results": [result.to_payload() for result in self.results],
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> QualityRun:
        if not isinstance(payload, Mapping) or set(payload) != {
            "id",
            "asset",
            "execution_ref",
            "results",
        }:
            raise ValueError("quality run has invalid shape")
        identifier = payload["id"]
        execution_ref = payload["execution_ref"]
        results = payload["results"]
        if not isinstance(identifier, str):
            raise ValueError("quality run id must be string")
        if execution_ref is not None and not isinstance(execution_ref, str):
            raise ValueError("quality execution_ref must be string or null")
        if not isinstance(results, list):
            raise ValueError("quality run results must be an array")
        return cls(
            QualityRunId(identifier),
            AssetRef.from_payload(payload["asset"]),
            cast(str | None, execution_ref),
            tuple(QualityResult.from_payload(result) for result in results),
        )

    @classmethod
    def from_json(cls, payload: str) -> QualityRun:
        return cls.from_payload(decode_canonical_json(payload))
