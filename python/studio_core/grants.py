"""Versioned provider-neutral authorization grants and requirements."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast
from urllib.parse import quote, unquote

from .canonical_json import decode as decode_canonical_json
from .canonical_json import encode as encode_canonical_json

ResourceKind: TypeAlias = Literal["project", "job", "run", "evidence", "*"]
Action: TypeAlias = Literal[
    "read",
    "list",
    "events",
    "submit",
    "execute",
    "cancel",
    "evidence:read",
]
DecisionReason: TypeAlias = Literal[
    "allowed",
    "no_matching_grant",
    "ambiguous",
    "unsupported_constraints",
]

GRANT_SCHEMA_VERSION = 1
RESOURCE_KINDS: frozenset[str] = frozenset({"project", "job", "run", "evidence", "*"})
ACTIONS: frozenset[str] = frozenset(
    {"read", "list", "events", "submit", "execute", "cancel", "evidence:read"}
)
MAX_GRANTS = 128
MAX_ACTIONS_PER_GRANT = len(ACTIONS)
MAX_CONSTRAINTS = 16
_MAX_TEXT_LENGTH = 256
_MAX_CONSTRAINT_KEY_LENGTH = 64
_SENSITIVE_CONSTRAINT_TERMS = (
    "password",
    "secret",
    "token",
    "credential",
    "api_key",
    "api-key",
    "private_key",
    "private-key",
    "access_key",
    "access-key",
)


def _require_text(value: str, name: str, *, maximum: int = _MAX_TEXT_LENGTH) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    if len(value) > maximum:
        raise ValueError(f"{name} must be at most {maximum} characters")
    return value


def _require_action(value: str) -> Action:
    if value not in ACTIONS:
        raise ValueError("unsupported authorization action")
    return cast(Action, value)


def _require_resource_kind(value: str) -> ResourceKind:
    if value not in RESOURCE_KINDS:
        raise ValueError("unsupported authorization resource kind")
    return cast(ResourceKind, value)


def _constraint_items(
    value: Mapping[str, str] | tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    items = tuple(value.items()) if isinstance(value, Mapping) else tuple(value)
    if len(items) > MAX_CONSTRAINTS:
        raise ValueError(
            f"authorization constraints must contain at most {MAX_CONSTRAINTS} entries"
        )
    normalized: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key, constraint_value in items:
        if not isinstance(key, str) or not isinstance(constraint_value, str):
            raise ValueError("authorization constraint keys and values must be strings")
        _require_text(key, "authorization constraint key", maximum=_MAX_CONSTRAINT_KEY_LENGTH)
        _require_text(constraint_value, "authorization constraint value")
        folded_key = key.casefold()
        if any(term in folded_key for term in _SENSITIVE_CONSTRAINT_TERMS):
            raise ValueError("authorization constraints must not contain credential material")
        folded_value = constraint_value.casefold()
        if folded_value.startswith("bearer ") or (
            "-----begin " in folded_value and "private key-----" in folded_value
        ):
            raise ValueError("authorization constraints must not contain credential material")
        if key in seen:
            raise ValueError("authorization constraint keys must be unique")
        seen.add(key)
        normalized.append((key, constraint_value))
    return tuple(sorted(normalized))


@dataclass(frozen=True, slots=True, order=True)
class ResourceScope:
    """One explicit resource kind and either an exact identifier or a kind wildcard."""

    kind: ResourceKind
    identifier: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _require_resource_kind(self.kind))
        if self.kind == "*":
            if self.identifier is not None:
                raise ValueError("global resource scope cannot carry an identifier")
            return
        if self.identifier is not None:
            _require_text(self.identifier, "authorization resource identifier")

    def to_payload(self) -> dict[str, object]:
        return {"kind": self.kind, "identifier": self.identifier}

    @classmethod
    def from_payload(cls, payload: object) -> ResourceScope:
        if not isinstance(payload, dict) or set(payload) != {"kind", "identifier"}:
            raise ValueError("authorization resource must contain exactly kind and identifier")
        kind = payload["kind"]
        identifier = payload["identifier"]
        if not isinstance(kind, str) or (
            identifier is not None and not isinstance(identifier, str)
        ):
            raise ValueError("authorization resource has invalid field types")
        return cls(_require_resource_kind(kind), cast(str | None, identifier))


@dataclass(frozen=True, slots=True)
class Requirement:
    """Requested authorization requirement, separate from grants and decisions."""

    action: Action
    resource: ResourceScope
    version: int = GRANT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.version != GRANT_SCHEMA_VERSION:
            raise ValueError("unsupported authorization requirement version")
        object.__setattr__(self, "action", _require_action(self.action))

    @property
    def canonical_key(self) -> tuple[str, str, str]:
        return (self.action, self.resource.kind, self.resource.identifier or "")

    def to_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "action": self.action,
            "resource": self.resource.to_payload(),
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> Requirement:
        if not isinstance(payload, dict) or set(payload) != {"version", "action", "resource"}:
            raise ValueError("authorization requirement has invalid shape")
        version = payload["version"]
        action = payload["action"]
        if not isinstance(version, int) or isinstance(version, bool) or not isinstance(action, str):
            raise ValueError("authorization requirement has invalid field types")
        return cls(_require_action(action), ResourceScope.from_payload(payload["resource"]), version)


@dataclass(frozen=True, slots=True)
class Grant:
    """Effective authorization grant. Constraint values are policy data, never credentials."""

    actions: frozenset[Action]
    resource: ResourceScope
    constraints: tuple[tuple[str, str], ...] = ()
    version: int = GRANT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.version != GRANT_SCHEMA_VERSION:
            raise ValueError("unsupported authorization grant version")
        actions = frozenset(_require_action(action) for action in self.actions)
        if not actions:
            raise ValueError("authorization grant must contain at least one action")
        if len(actions) > MAX_ACTIONS_PER_GRANT:
            raise ValueError("authorization grant contains too many actions")
        object.__setattr__(self, "actions", actions)
        object.__setattr__(self, "constraints", _constraint_items(self.constraints))

    @property
    def canonical_key(self) -> tuple[tuple[str, ...], str, str, tuple[tuple[str, str], ...]]:
        return (
            tuple(sorted(self.actions)),
            self.resource.kind,
            self.resource.identifier or "",
            self.constraints,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "actions": sorted(self.actions),
            "resource": self.resource.to_payload(),
            "constraints": dict(self.constraints),
        }

    @classmethod
    def from_payload(cls, payload: object) -> Grant:
        if not isinstance(payload, dict):
            raise ValueError("authorization grant must be a JSON object")
        allowed_keys = {"version", "actions", "resource", "constraints"}
        if set(payload) - allowed_keys or not {"version", "actions", "resource"}.issubset(payload):
            raise ValueError("authorization grant has invalid shape")
        version = payload["version"]
        actions = payload["actions"]
        constraints = payload.get("constraints", {})
        if not isinstance(version, int) or isinstance(version, bool):
            raise ValueError("authorization grant version must be an integer")
        if not isinstance(actions, list) or not all(isinstance(action, str) for action in actions):
            raise ValueError("authorization grant actions must be a JSON string array")
        if not isinstance(constraints, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in constraints.items()
        ):
            raise ValueError("authorization grant constraints must be a JSON string object")
        return cls(
            frozenset(_require_action(cast(str, action)) for action in actions),
            ResourceScope.from_payload(payload["resource"]),
            _constraint_items(cast(dict[str, str], constraints)),
            version,
        )

    def requirements(self) -> tuple[Requirement, ...]:
        """Expand an unconstrained v0.1 bearer grant into exact execution requirements."""
        if self.constraints:
            raise ValueError("constrained grants cannot be losslessly mapped to v0.1 bearer scopes")
        return tuple(Requirement(action, self.resource) for action in sorted(self.actions))


@dataclass(frozen=True, slots=True)
class Decision:
    """Pure policy decision, separate from the request and enforcement evidence."""

    allowed: bool
    reason: DecisionReason
    matched_grant: Grant | None = None

    def __post_init__(self) -> None:
        if self.allowed:
            if self.reason != "allowed" or self.matched_grant is None:
                raise ValueError("allowed authorization decision requires a matched grant")
        elif self.reason == "allowed" or self.matched_grant is not None:
            raise ValueError("denied authorization decision cannot carry an allowed match")

    def to_payload(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "matched_grant": (
                None if self.matched_grant is None else self.matched_grant.to_payload()
            ),
        }


@dataclass(frozen=True, slots=True)
class AuthorizationEvidence:
    """Observed enforcement evidence emitted only after a concrete decision is evaluated."""

    enforcement_point: str
    requirement: Requirement
    decision: Decision
    version: int = GRANT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.version != GRANT_SCHEMA_VERSION:
            raise ValueError("unsupported authorization evidence version")
        _require_text(self.enforcement_point, "authorization enforcement point")

    def to_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "enforcement_point": self.enforcement_point,
            "requirement": self.requirement.to_payload(),
            "decision": self.decision.to_payload(),
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")


def _resource_covers(grant: ResourceScope, requirement: ResourceScope) -> bool:
    if grant.kind == "*":
        return True
    if grant.kind != requirement.kind:
        return False
    if grant.identifier is None:
        return True
    return requirement.identifier is not None and grant.identifier == requirement.identifier


def _specificity(scope: ResourceScope) -> int:
    if scope.kind == "*":
        return 0
    return 1 if scope.identifier is None else 2


@dataclass(frozen=True, slots=True)
class GrantSet:
    """Canonical grant collection with deterministic deny-by-default matching."""

    grants: tuple[Grant, ...] = ()
    version: int = GRANT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.version != GRANT_SCHEMA_VERSION:
            raise ValueError("unsupported authorization grant-set version")
        if len(self.grants) > MAX_GRANTS:
            raise ValueError(f"authorization grant set must contain at most {MAX_GRANTS} grants")
        grants = tuple(sorted(self.grants, key=lambda grant: grant.canonical_key))
        if len(set(grants)) != len(grants):
            raise ValueError("authorization grants must be unique")
        object.__setattr__(self, "grants", grants)

    def permits(self, requirement: Requirement) -> Decision:
        candidates = tuple(
            grant
            for grant in self.grants
            if (
                requirement.action in grant.actions
                and _resource_covers(grant.resource, requirement.resource)
            )
        )
        supported = tuple(grant for grant in candidates if not grant.constraints)
        if not supported:
            if candidates:
                return Decision(False, "unsupported_constraints")
            return Decision(False, "no_matching_grant")

        highest = max(_specificity(grant.resource) for grant in supported)
        most_specific = tuple(
            grant for grant in supported if _specificity(grant.resource) == highest
        )
        if len(most_specific) != 1:
            return Decision(False, "ambiguous")
        return Decision(True, "allowed", most_specific[0])

    def to_payload(self) -> dict[str, object]:
        return {"version": self.version, "grants": [grant.to_payload() for grant in self.grants]}

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> GrantSet:
        if not isinstance(payload, dict) or set(payload) != {"version", "grants"}:
            raise ValueError("authorization grant set must contain exactly version and grants")
        version = payload["version"]
        grants = payload["grants"]
        if not isinstance(version, int) or isinstance(version, bool):
            raise ValueError("authorization grant-set version must be an integer")
        if not isinstance(grants, list):
            raise ValueError("authorization grant-set grants must be a JSON array")
        return cls(tuple(Grant.from_payload(item) for item in grants), version)

    @classmethod
    def from_json(cls, value: str) -> GrantSet:
        try:
            payload = decode_canonical_json(value)
        except ValueError as exc:
            raise ValueError("authorization grant set must be valid JSON") from exc
        return cls.from_payload(payload)

    def requirements(self) -> tuple[Requirement, ...]:
        """Losslessly expand unconstrained bearer-token grants to requirements."""
        requirements = [
            requirement
            for grant in self.grants
            for requirement in grant.requirements()
        ]
        return tuple(sorted(requirements, key=lambda item: item.canonical_key))


def requirement_to_bearer_scope(requirement: Requirement) -> str:
    """Encode one requirement as a stable v1 bearer-scope string."""
    identifier = "*" if requirement.resource.identifier is None else quote(
        requirement.resource.identifier, safe=""
    )
    return ":".join(
        (
            "ronin",
            "v1",
            quote(requirement.action, safe=""),
            quote(requirement.resource.kind, safe=""),
            identifier,
        )
    )


def _decode_scope_component(value: str, name: str) -> str:
    if re.search(r"%(?![0-9A-Fa-f]{2})", value):
        raise ValueError(f"bearer scope {name} contains invalid percent encoding")
    decoded = unquote(value)
    _require_text(decoded, f"bearer scope {name}")
    return decoded


def parse_bearer_scope(value: str) -> Requirement:
    """Parse a stable v1 bearer-scope string into a typed requirement."""
    _require_text(value, "bearer scope")
    parts = value.split(":", maxsplit=4)
    if len(parts) != 5 or parts[0] != "ronin" or parts[1] != "v1":
        raise ValueError("bearer scope must use ronin:v1:<action>:<resource-kind>:<identifier>")
    action = _require_action(_decode_scope_component(parts[2], "action"))
    kind = _require_resource_kind(_decode_scope_component(parts[3], "resource kind"))
    identifier = None if parts[4] == "*" else _decode_scope_component(parts[4], "identifier")
    requirement = Requirement(action, ResourceScope(kind, identifier))
    if requirement_to_bearer_scope(requirement) != value:
        raise ValueError("bearer scope must use canonical v1 encoding")
    return requirement


def parse_legacy_permission(value: str) -> Requirement:
    """Alpha migration parser for explicit typed permissions embedded in legacy strings."""
    return parse_bearer_scope(value)


__all__ = (
    "ACTIONS",
    "GRANT_SCHEMA_VERSION",
    "MAX_CONSTRAINTS",
    "MAX_GRANTS",
    "RESOURCE_KINDS",
    "Action",
    "AuthorizationEvidence",
    "Decision",
    "DecisionReason",
    "Grant",
    "GrantSet",
    "Requirement",
    "ResourceKind",
    "ResourceScope",
    "parse_bearer_scope",
    "parse_legacy_permission",
    "requirement_to_bearer_scope",
)
