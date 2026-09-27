"""Versioned ownership and stewardship metadata for governed assets."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .canonical_json import decode as decode_canonical_json
from .canonical_json import encode as encode_canonical_json


def _refs(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    result = tuple(sorted(value.strip() for value in values))
    if any(not value for value in result) or len(result) != len(set(result)):
        raise ValueError(f"{field} must contain unique non-empty references")
    return result


@dataclass(frozen=True, slots=True)
class OwnershipMetadata:
    version: int
    owner_ref: str
    steward_refs: tuple[str, ...] = ()
    domain: str | None = None
    lifecycle: str = "active"

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("ownership metadata version must be positive")
        owner = self.owner_ref.strip()
        if not owner:
            raise ValueError("owner_ref must be non-empty")
        object.__setattr__(self, "owner_ref", owner)
        object.__setattr__(self, "steward_refs", _refs(self.steward_refs, "steward_refs"))
        if self.domain is not None:
            domain = self.domain.strip()
            if not domain:
                raise ValueError("domain must be non-empty when provided")
            object.__setattr__(self, "domain", domain)
        if self.lifecycle not in {"active", "deprecated", "retired"}:
            raise ValueError("unsupported ownership lifecycle")

    def to_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "owner_ref": self.owner_ref,
            "steward_refs": list(self.steward_refs),
            "domain": self.domain,
            "lifecycle": self.lifecycle,
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> OwnershipMetadata:
        if not isinstance(payload, Mapping) or set(payload) != {
            "version",
            "owner_ref",
            "steward_refs",
            "domain",
            "lifecycle",
        }:
            raise ValueError("ownership metadata has invalid shape")
        if not isinstance(payload["version"], int) or isinstance(payload["version"], bool):
            raise ValueError("ownership metadata version must be an integer")
        if not isinstance(payload["owner_ref"], str) or not isinstance(payload["lifecycle"], str):
            raise ValueError("ownership metadata scalar fields have invalid types")
        stewards = payload["steward_refs"]
        if not isinstance(stewards, list) or not all(isinstance(value, str) for value in stewards):
            raise ValueError("steward_refs must be a string array")
        domain = payload["domain"]
        if domain is not None and not isinstance(domain, str):
            raise ValueError("domain must be a string or null")
        return cls(
            payload["version"],
            payload["owner_ref"],
            tuple(stewards),
            domain,
            payload["lifecycle"],
        )

    @classmethod
    def from_json(cls, payload: str) -> OwnershipMetadata:
        return cls.from_payload(decode_canonical_json(payload))


__all__ = ("OwnershipMetadata",)
