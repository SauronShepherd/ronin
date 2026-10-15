"""Deterministic blueprint extraction and conformance contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from studio_core.canonical_json import encode as encode_canonical_json

RuleClass = Literal["MANDATORY", "DERIVED", "ADVISORY"]


@dataclass(frozen=True, slots=True, order=True)
class BlueprintRule:
    rule_id: str
    classification: RuleClass
    evidence: str
    effect: str


@dataclass(frozen=True, slots=True)
class BlueprintContract:
    source_digest: str
    rules: tuple[BlueprintRule, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "rules", tuple(sorted(self.rules)))

    @property
    def digest(self) -> str:
        payload = {
            "source_digest": self.source_digest,
            "rules": [
                {
                    "rule_id": item.rule_id,
                    "classification": item.classification,
                    "evidence": item.evidence,
                    "effect": item.effect,
                }
                for item in self.rules
            ],
        }
        return hashlib.sha256(encode_canonical_json(payload)).hexdigest()


def extract_blueprint(document: str | bytes) -> BlueprintContract:
    """Extract only explicit, auditable conventions from a JSON reference project."""
    try:
        payload = json.loads(document)
    except (TypeError, ValueError) as exc:
        raise ValueError("blueprint is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("blueprint root must be an object")
    rules: list[BlueprintRule] = []
    conventions = payload.get("conventions", {})
    if not isinstance(conventions, dict):
        raise ValueError("blueprint conventions must be an object")
    for key, value in sorted(conventions.items()):
        if not isinstance(key, str) or not isinstance(value, str) or not value.strip():
            raise ValueError("blueprint conventions require string key/value pairs")
        rules.append(BlueprintRule(f"convention.{key}", "MANDATORY", f"conventions.{key}", value))
    topology = payload.get("topology")
    if topology is not None:
        if not isinstance(topology, str) or not topology.strip():
            raise ValueError("blueprint topology must be a non-empty string")
        rules.append(BlueprintRule("project.topology", "DERIVED", "topology", topology))
    digest = hashlib.sha256(encode_canonical_json(payload)).hexdigest()
    return BlueprintContract(digest, tuple(rules))


__all__ = ("BlueprintContract", "BlueprintRule", "extract_blueprint")
