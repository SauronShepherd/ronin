"""Canonical, secret-free manifest for reproducible development/deployment."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from .canonical_json import decode as decode_canonical_json
from .canonical_json import encode as encode_canonical_json

REPRODUCIBLE_MANIFEST_SCHEMA = "ronin.reproducible-manifest/v1"


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty trimmed text")
    if any(char in value for char in "\r\n\x00"):
        raise ValueError(f"{name} must be single-line text")
    return value


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise TypeError(f"{name} must be an object with string keys")
    return cast(Mapping[str, object], value)


def _text_map(value: object, name: str) -> tuple[tuple[str, str], ...]:
    values = _mapping(value, name)
    return tuple(
        sorted(
            (_text(key, f"{name} key"), _text(item, f"{name}.{key}"))
            for key, item in values.items()
        )
    )


@dataclass(frozen=True, slots=True)
class ReproducibleManifest:
    """All non-secret inputs needed to identify a reproducible execution."""

    source_revision: str
    environment: str
    runtime_profile: str
    dependency_locks: tuple[tuple[str, str], ...]
    plugin_lock: str
    configuration: tuple[tuple[str, str], ...]
    execution_profile: str
    migration_policy: str = "fail-closed"
    schema: str = REPRODUCIBLE_MANIFEST_SCHEMA

    def __post_init__(self) -> None:
        _text(self.source_revision, "source_revision")
        _text(self.environment, "environment")
        _text(self.runtime_profile, "runtime_profile")
        _text(self.plugin_lock, "plugin_lock")
        _text(self.execution_profile, "execution_profile")
        if self.migration_policy not in {"fail-closed", "forward-compatible"}:
            raise ValueError("migration_policy must be fail-closed or forward-compatible")
        if self.schema != REPRODUCIBLE_MANIFEST_SCHEMA:
            raise ValueError(f"unsupported reproducible manifest schema: {self.schema}")
        for name, values in (
            ("dependency_locks", self.dependency_locks),
            ("configuration", self.configuration),
        ):
            if tuple(sorted(values)) != values or len({key for key, _ in values}) != len(values):
                raise ValueError(f"{name} must be sorted and contain unique keys")
            for key, value in values:
                _text(key, f"{name} key")
                _text(value, f"{name}.{key}")
        if any(
            key.lower().endswith(("secret", "token", "password", "private_key"))
            for key, _ in self.configuration
        ):
            raise ValueError(
                "reproducible manifest configuration must not contain secret-like keys"
            )

    @property
    def identity(self) -> str:
        """Stable content identity over the canonical manifest payload."""
        import hashlib

        return hashlib.sha256(self.to_json().encode()).hexdigest()

    def to_data(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "source_revision": self.source_revision,
            "environment": self.environment,
            "runtime_profile": self.runtime_profile,
            "dependency_locks": dict(self.dependency_locks),
            "plugin_lock": self.plugin_lock,
            "configuration": dict(self.configuration),
            "execution_profile": self.execution_profile,
            "migration_policy": self.migration_policy,
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_data()).decode()

    @classmethod
    def from_data(cls, value: Mapping[str, object]) -> ReproducibleManifest:
        data = _mapping(value, "manifest")
        expected = {
            "schema",
            "source_revision",
            "environment",
            "runtime_profile",
            "dependency_locks",
            "plugin_lock",
            "configuration",
            "execution_profile",
            "migration_policy",
        }
        if set(data) != expected:
            raise ValueError(f"manifest keys mismatch; expected={sorted(expected)}")
        return cls(
            source_revision=_text(data["source_revision"], "source_revision"),
            environment=_text(data["environment"], "environment"),
            runtime_profile=_text(data["runtime_profile"], "runtime_profile"),
            dependency_locks=_text_map(data["dependency_locks"], "dependency_locks"),
            plugin_lock=_text(data["plugin_lock"], "plugin_lock"),
            configuration=_text_map(data["configuration"], "configuration"),
            execution_profile=_text(data["execution_profile"], "execution_profile"),
            migration_policy=_text(data["migration_policy"], "migration_policy"),
            schema=_text(data["schema"], "schema"),
        )

    @classmethod
    def from_json(cls, payload: str) -> ReproducibleManifest:
        return cls.from_data(_mapping(decode_canonical_json(payload), "manifest"))


__all__ = ("REPRODUCIBLE_MANIFEST_SCHEMA", "ReproducibleManifest")
