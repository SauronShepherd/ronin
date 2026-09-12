"""Provider-neutral environment and deployment-binding contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeAlias, cast
from urllib.parse import urlsplit

from .canonical_json import decode as decode_canonical_json
from .canonical_json import encode as encode_canonical_json
from .portability import BINDING_KINDS, BindingKind
from .projects import ProjectId

EnvironmentState: TypeAlias = str
_ALLOWED_STATES = frozenset({"active", "disabled"})
_EXPECTED_SCHEMES: dict[str, str] = {
    "connection": "connection",
    "secret": "secret",
    "runtime": "runtime",
    "identity": "identity",
    "notification": "notification",
    "model_provider": "model-provider",
    "storage": "storage",
    "endpoint": "endpoint",
}
_SENSITIVE_TERMS = (
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
)


def _require_text(value: str, name: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    return value


def _safe_ref(value: str, name: str) -> str:
    value = _require_text(value, name)
    folded = value.casefold()
    if any(term in folded for term in _SENSITIVE_TERMS):
        raise ValueError(f"{name} must not contain credential material")
    return value


@dataclass(frozen=True, order=True, slots=True)
class EnvironmentId:
    value: str

    def __post_init__(self) -> None:
        _require_text(self.value, "environment id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class EnvironmentDefinition:
    id: EnvironmentId
    name: str
    description: str = ""
    state: EnvironmentState = "active"

    def __post_init__(self) -> None:
        _require_text(self.name, "environment name")
        if self.description and (
            self.description != self.description.strip()
            or "\x00" in self.description
        ):
            raise ValueError("environment description must be trimmed and contain no NUL")
        if self.state not in _ALLOWED_STATES:
            raise ValueError("environment state must be active or disabled")

    @property
    def disabled(self) -> bool:
        return self.state == "disabled"

    def to_payload(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "state": self.state,
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> EnvironmentDefinition:
        if not isinstance(payload, Mapping) or set(payload) != {
            "id",
            "name",
            "description",
            "state",
        }:
            raise ValueError("environment definition has invalid shape")
        environment_id = payload["id"]
        name = payload["name"]
        description = payload["description"]
        state = payload["state"]
        if not all(isinstance(value, str) for value in (environment_id, name, description, state)):
            raise ValueError("environment definition fields must be strings")
        return cls(
            EnvironmentId(cast(str, environment_id)),
            cast(str, name),
            cast(str, description),
            cast(str, state),
        )

    @classmethod
    def from_json(cls, payload: str) -> EnvironmentDefinition:
        return cls.from_payload(decode_canonical_json(payload))


@dataclass(frozen=True, order=True, slots=True)
class DeploymentBinding:
    """Map a portable logical reference to one environment-local resource reference."""

    kind: BindingKind
    source_ref: str
    target_ref: str

    def __post_init__(self) -> None:
        if self.kind not in BINDING_KINDS:
            raise ValueError("unsupported deployment binding kind")
        object.__setattr__(self, "source_ref", _safe_ref(self.source_ref, "binding source_ref"))
        target = _safe_ref(self.target_ref, "binding target_ref")
        parsed = urlsplit(target)
        expected = _EXPECTED_SCHEMES[self.kind]
        if parsed.scheme != expected:
            raise ValueError(f"{self.kind} binding target must use {expected}://")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("binding target must not embed credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("binding target must not contain query or fragment components")
        if not parsed.netloc and not parsed.path:
            raise ValueError("binding target must identify a resource")
        object.__setattr__(self, "target_ref", target)

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "source_ref": self.source_ref,
            "target_ref": self.target_ref,
        }

    @classmethod
    def from_payload(cls, payload: object) -> DeploymentBinding:
        if not isinstance(payload, Mapping) or set(payload) != {
            "kind",
            "source_ref",
            "target_ref",
        }:
            raise ValueError("deployment binding has invalid shape")
        kind = payload["kind"]
        source_ref = payload["source_ref"]
        target_ref = payload["target_ref"]
        if not all(isinstance(value, str) for value in (kind, source_ref, target_ref)):
            raise ValueError("deployment binding fields must be strings")
        if kind not in BINDING_KINDS:
            raise ValueError("unsupported deployment binding kind")
        return cls(cast(BindingKind, kind), cast(str, source_ref), cast(str, target_ref))


@dataclass(frozen=True, slots=True)
class ProjectEnvironmentBindings:
    project_id: ProjectId
    environment_id: EnvironmentId
    bindings: tuple[DeploymentBinding, ...] = ()

    def __post_init__(self) -> None:
        bindings = tuple(sorted(self.bindings))
        keys = [(binding.kind, binding.source_ref) for binding in bindings]
        if len(keys) != len(set(keys)):
            raise ValueError("project environment bindings must be unique by kind/source_ref")
        object.__setattr__(self, "bindings", bindings)

    def resolve(self, kind: BindingKind, source_ref: str) -> str | None:
        for binding in self.bindings:
            if binding.kind == kind and binding.source_ref == source_ref:
                return binding.target_ref
        return None

    def to_payload(self) -> dict[str, object]:
        return {
            "project_id": str(self.project_id),
            "environment_id": str(self.environment_id),
            "bindings": [binding.to_payload() for binding in self.bindings],
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> ProjectEnvironmentBindings:
        if not isinstance(payload, Mapping) or set(payload) != {
            "project_id",
            "environment_id",
            "bindings",
        }:
            raise ValueError("project environment bindings have invalid shape")
        project_id = payload["project_id"]
        environment_id = payload["environment_id"]
        bindings = payload["bindings"]
        if not isinstance(project_id, str) or not isinstance(environment_id, str):
            raise ValueError("project/environment ids must be strings")
        if not isinstance(bindings, list):
            raise ValueError("bindings must be an array")
        return cls(
            ProjectId(project_id),
            EnvironmentId(environment_id),
            tuple(DeploymentBinding.from_payload(item) for item in bindings),
        )

    @classmethod
    def from_json(cls, payload: str) -> ProjectEnvironmentBindings:
        return cls.from_payload(decode_canonical_json(payload))


__all__ = (
    "DeploymentBinding",
    "EnvironmentDefinition",
    "EnvironmentId",
    "EnvironmentState",
    "ProjectEnvironmentBindings",
)
