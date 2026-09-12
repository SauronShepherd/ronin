"""Append-only audit event contracts for Ronin Public v1."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from .canonical_json import decode as decode_canonical_json
from .canonical_json import encode as encode_canonical_json

ActorKind: TypeAlias = Literal["user", "service", "local", "token"]
AuditOutcome: TypeAlias = Literal["succeeded", "failed", "allowed", "denied"]


def _require_text(value: str, name: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    return value


def _metadata(values: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key, value in values:
        key = _require_text(key, "audit metadata key")
        value = _require_text(value, "audit metadata value")
        folded = key.casefold()
        if any(term in folded for term in ("password", "secret", "token", "credential", "api_key")):
            raise ValueError("audit metadata must not contain credential-bearing keys")
        folded_value = value.casefold()
        if folded_value.startswith("bearer ") or "-----begin " in folded_value:
            raise ValueError("audit metadata must not contain credential material")
        if key in seen:
            raise ValueError("audit metadata keys must be unique")
        seen.add(key)
        result.append((key, value))
    return tuple(sorted(result))


@dataclass(frozen=True, order=True, slots=True)
class AuditEventId:
    value: str

    def __post_init__(self) -> None:
        _require_text(self.value, "audit event id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True, slots=True)
class AuditActor:
    kind: ActorKind
    ref: str

    def __post_init__(self) -> None:
        if self.kind not in {"user", "service", "local", "token"}:
            raise ValueError("unsupported audit actor kind")
        _require_text(self.ref, "audit actor ref")

    def to_payload(self) -> dict[str, str]:
        return {"kind": self.kind, "ref": self.ref}

    @classmethod
    def from_payload(cls, payload: object) -> AuditActor:
        if not isinstance(payload, Mapping) or set(payload) != {"kind", "ref"}:
            raise ValueError("audit actor has invalid shape")
        kind = payload["kind"]
        ref = payload["ref"]
        if not isinstance(kind, str) or kind not in {"user", "service", "local", "token"}:
            raise ValueError("unsupported audit actor kind")
        if not isinstance(ref, str):
            raise ValueError("audit actor ref must be string")
        return cls(cast(ActorKind, kind), ref)


@dataclass(frozen=True, order=True, slots=True)
class AuditResource:
    kind: str
    ref: str

    def __post_init__(self) -> None:
        _require_text(self.kind, "audit resource kind")
        _require_text(self.ref, "audit resource ref")

    def to_payload(self) -> dict[str, str]:
        return {"kind": self.kind, "ref": self.ref}

    @classmethod
    def from_payload(cls, payload: object) -> AuditResource:
        if not isinstance(payload, Mapping) or set(payload) != {"kind", "ref"}:
            raise ValueError("audit resource has invalid shape")
        kind = payload["kind"]
        ref = payload["ref"]
        if not isinstance(kind, str) or not isinstance(ref, str):
            raise ValueError("audit resource fields must be strings")
        return cls(kind, ref)


@dataclass(frozen=True, slots=True)
class AuditEvent:
    id: AuditEventId
    occurred_at: str
    actor: AuditActor
    action: str
    resource: AuditResource
    outcome: AuditOutcome
    request_id: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.occurred_at, "audit occurred_at")
        _require_text(self.action, "audit action")
        if self.outcome not in {"succeeded", "failed", "allowed", "denied"}:
            raise ValueError("unsupported audit outcome")
        if self.request_id is not None:
            _require_text(self.request_id, "audit request_id")
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id.value,
            "occurred_at": self.occurred_at,
            "actor": self.actor.to_payload(),
            "action": self.action,
            "resource": self.resource.to_payload(),
            "outcome": self.outcome,
            "request_id": self.request_id,
            "metadata": dict(self.metadata),
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(encode_canonical_json(self.to_payload())).hexdigest()

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> AuditEvent:
        if not isinstance(payload, Mapping) or set(payload) != {
            "id",
            "occurred_at",
            "actor",
            "action",
            "resource",
            "outcome",
            "request_id",
            "metadata",
        }:
            raise ValueError("audit event has invalid shape")
        identifier = payload["id"]
        occurred_at = payload["occurred_at"]
        action = payload["action"]
        outcome = payload["outcome"]
        request_id = payload["request_id"]
        metadata = payload["metadata"]
        if not all(isinstance(value, str) for value in (identifier, occurred_at, action, outcome)):
            raise ValueError("audit event identity/action/outcome fields must be strings")
        if outcome not in {"succeeded", "failed", "allowed", "denied"}:
            raise ValueError("unsupported audit outcome")
        if request_id is not None and not isinstance(request_id, str):
            raise ValueError("audit request_id must be string or null")
        if not isinstance(metadata, Mapping) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in metadata.items()
        ):
            raise ValueError("audit metadata must be string object")
        return cls(
            AuditEventId(cast(str, identifier)),
            cast(str, occurred_at),
            AuditActor.from_payload(payload["actor"]),
            cast(str, action),
            AuditResource.from_payload(payload["resource"]),
            cast(AuditOutcome, outcome),
            cast(str | None, request_id),
            tuple(sorted(cast(Mapping[str, str], metadata).items())),
        )

    @classmethod
    def from_json(cls, payload: str) -> AuditEvent:
        return cls.from_payload(decode_canonical_json(payload))
