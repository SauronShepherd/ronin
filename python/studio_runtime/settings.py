"""Namespaced, validated plugin configuration with secret redaction."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


class PluginSettingsError(ValueError):
    """A plugin settings schema or value is invalid."""


@dataclass(frozen=True, slots=True)
class SecretReference:
    """Portable reference to a secret; the referenced value never enters settings."""

    uri: str

    def __post_init__(self) -> None:
        if not self.uri.startswith("secret://") or len(self.uri) <= len("secret://"):
            raise PluginSettingsError("secret references must use a non-empty secret:// URI")


@dataclass(frozen=True, slots=True)
class PluginSettingsSpec:
    plugin_id: str
    keys: tuple[str, ...] = ()
    defaults: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))
    secret_keys: frozenset[str] = frozenset()
    reloadable_keys: frozenset[str] = frozenset()

    def validate(self) -> None:
        if not self.plugin_id or any(not key or key != key.upper() for key in self.keys):
            raise PluginSettingsError(f"invalid settings schema for {self.plugin_id!r}")
        if len(set(self.keys)) != len(self.keys):
            raise PluginSettingsError(f"duplicate settings key in {self.plugin_id}")
        allowed = set(self.keys)
        if not set(self.defaults) <= allowed:
            raise PluginSettingsError(f"default uses unknown key in {self.plugin_id}")
        if not self.secret_keys <= allowed or not self.reloadable_keys <= allowed:
            raise PluginSettingsError(f"settings metadata uses unknown key in {self.plugin_id}")


class PluginSettingsRegistry:
    """Loads settings only under ``RONIN_PLUGIN_<ID>_`` namespaces."""

    def __init__(self) -> None:
        self._specs: dict[str, PluginSettingsSpec] = {}
        self._values: dict[str, dict[str, object]] = {}

    def register(self, spec: PluginSettingsSpec) -> None:
        spec.validate()
        if spec.plugin_id in self._specs:
            raise PluginSettingsError(f"settings schema collision: {spec.plugin_id}")
        self._specs[spec.plugin_id] = spec

    @property
    def plugin_ids(self) -> frozenset[str]:
        return frozenset(self._specs)

    def load(self, environ: Mapping[str, str] | None = None) -> None:
        source = os.environ if environ is None else environ
        for plugin_id, spec in self._specs.items():
            prefix = f"RONIN_PLUGIN_{plugin_id.upper().replace('.', '_').replace('-', '_')}_"
            values = dict(spec.defaults)
            for key, value in source.items():
                if not key.startswith(prefix):
                    continue
                setting = key[len(prefix) :]
                if setting not in spec.keys:
                    raise PluginSettingsError(f"unknown setting {key} for {plugin_id}")
                if not value.strip():
                    raise PluginSettingsError(f"setting {key} must not be empty")
                if setting in spec.secret_keys and not value.startswith("secret://"):
                    raise PluginSettingsError(f"secret setting {key} must be a secret:// reference")
                values[setting] = value
            self._values[plugin_id] = values

    def configure(self, plugin_id: str, values: Mapping[str, object]) -> None:
        spec = self._specs.get(plugin_id)
        if spec is None:
            raise PluginSettingsError(f"unknown plugin settings schema: {plugin_id}")
        unknown = set(values) - set(spec.keys)
        if unknown:
            raise PluginSettingsError(f"unknown settings for {plugin_id}: {sorted(unknown)}")
        for key in spec.secret_keys & set(values):
            value = values[key]
            if not isinstance(value, SecretReference) and not (
                isinstance(value, str) and value.startswith("secret://")
            ):
                raise PluginSettingsError(f"secret setting {key} must be a secret:// reference")
        merged = dict(spec.defaults)
        merged.update(values)
        self._values[plugin_id] = merged

    def get(self, plugin_id: str) -> Mapping[str, object]:
        if plugin_id not in self._specs:
            raise PluginSettingsError(f"unknown plugin settings schema: {plugin_id}")
        return MappingProxyType(dict(self._values.get(plugin_id, self._specs[plugin_id].defaults)))

    def redacted(self) -> dict[str, dict[str, object]]:
        result: dict[str, dict[str, object]] = {}
        for plugin_id, spec in self._specs.items():
            values = self._values.get(plugin_id, dict(spec.defaults))
            result[plugin_id] = {
                key: "[REDACTED]" if key in spec.secret_keys and key in values else value
                for key, value in sorted(values.items())
            }
        return result

    def reloadable(self) -> dict[str, tuple[str, ...]]:
        return {
            plugin_id: tuple(sorted(spec.reloadable_keys))
            for plugin_id, spec in sorted(self._specs.items())
        }

    def digest(self, plugin_id: str) -> str:
        """Return a stable digest over redacted effective settings for evidence."""
        payload = self.redacted().get(plugin_id)
        if payload is None:
            raise PluginSettingsError(f"unknown plugin settings schema: {plugin_id}")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        return hashlib.sha256(encoded).hexdigest()


__all__ = (
    "PluginSettingsError",
    "PluginSettingsRegistry",
    "PluginSettingsSpec",
    "SecretReference",
)
