"""Immutable, non-secret execution reproducibility evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

DigestKind: TypeAlias = Literal[
    "package_lock",
    "environment",
    "runtime_image",
    "runtime_artifact",
]

_SENSITIVE_TOKENS = frozenset(
    {
        "authorization",
        "credential",
        "credentials",
        "password",
        "passwd",
        "secret",
        "token",
    }
)


def _require_text(value: str, name: str) -> None:
    if not value or value.strip() != value or "\n" in value or "\r" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")


def _name_tokens(value: str) -> tuple[str, ...]:
    normalized = "".join(character if character.isalnum() else "_" for character in value.lower())
    return tuple(token for token in normalized.split("_") if token)


def _looks_sensitive_name(value: str) -> bool:
    tokens = _name_tokens(value)
    if any(token in _SENSITIVE_TOKENS for token in tokens):
        return True
    pairs = set(zip(tokens, tokens[1:], strict=False))
    return ("api", "key") in pairs or ("private", "key") in pairs


@dataclass(frozen=True, order=True, slots=True)
class ExecutionAttemptId:
    """Opaque durable attempt identity allocated by an orchestration boundary."""

    value: str

    def __post_init__(self) -> None:
        _require_text(self.value, "execution attempt id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True, slots=True)
class ExecutionEventId:
    """Stable event identity inside one durable execution attempt."""

    attempt_id: ExecutionAttemptId
    sequence: int

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("execution event sequence must be non-negative")


@dataclass(frozen=True, order=True, slots=True)
class EffectiveRuntimeSetting:
    """Adapter-normalized effective configuration safe to persist as evidence."""

    name: str
    value: str

    def __post_init__(self) -> None:
        _require_text(self.name, "runtime setting name")
        _require_text(self.value, "runtime setting value")
        if _looks_sensitive_name(self.name):
            raise ValueError("runtime setting name appears to contain secret material")


@dataclass(frozen=True, order=True, slots=True)
class ReproducibilityDigest:
    """SHA-256 identity for one package/environment/image/runtime artifact."""

    kind: DigestKind
    reference: str
    sha256: str

    def __post_init__(self) -> None:
        if self.kind not in {
            "package_lock",
            "environment",
            "runtime_image",
            "runtime_artifact",
        }:
            raise ValueError("unsupported reproducibility digest kind")
        _require_text(self.reference, "reproducibility digest reference")
        if len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise ValueError("reproducibility digest must be a lowercase SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class ExecutionReproducibilitySnapshot:
    """Canonical effective runtime state captured before side effects begin."""

    settings: tuple[EffectiveRuntimeSetting, ...] = ()
    digests: tuple[ReproducibilityDigest, ...] = ()

    def __post_init__(self) -> None:
        settings = tuple(sorted(self.settings))
        setting_names = tuple(setting.name for setting in settings)
        if len(set(setting_names)) != len(setting_names):
            raise ValueError("effective runtime setting names must be unique")

        digests = tuple(sorted(self.digests))
        digest_keys = tuple((digest.kind, digest.reference) for digest in digests)
        if len(set(digest_keys)) != len(digest_keys):
            raise ValueError("reproducibility digest kind/reference pairs must be unique")

        object.__setattr__(self, "settings", settings)
        object.__setattr__(self, "digests", digests)
