from __future__ import annotations

from types import MappingProxyType

import pytest
from studio_runtime import (
    PluginSettingsError,
    PluginSettingsRegistry,
    PluginSettingsSpec,
    SecretReference,
)


def test_settings_are_namespaced_and_redacted() -> None:
    registry = PluginSettingsRegistry()
    registry.register(
        PluginSettingsSpec(
            "example",
            keys=("ENDPOINT", "TOKEN", "TIMEOUT"),
            defaults={"TIMEOUT": 30},
            secret_keys=frozenset({"TOKEN"}),
            reloadable_keys=frozenset({"TIMEOUT"}),
        )
    )
    registry.load(
        {
            "RONIN_PLUGIN_EXAMPLE_ENDPOINT": "https://example",
            "RONIN_PLUGIN_EXAMPLE_TOKEN": "secret://vault/example-token",
        }
    )

    assert registry.get("example")["ENDPOINT"] == "https://example"
    assert registry.redacted()["example"]["TOKEN"] == "[REDACTED]"  # noqa: S105
    assert registry.get("example")["TIMEOUT"] == 30
    assert registry.reloadable()["example"] == ("TIMEOUT",)
    assert len(registry.digest("example")) == 64


def test_settings_reject_unknown_keys_and_empty_values() -> None:
    registry = PluginSettingsRegistry()
    registry.register(PluginSettingsSpec("example", keys=("TOKEN",)))

    with pytest.raises(PluginSettingsError, match="unknown setting"):
        registry.load({"RONIN_PLUGIN_EXAMPLE_UNKNOWN": "value"})
    with pytest.raises(PluginSettingsError, match="must not be empty"):
        registry.load({"RONIN_PLUGIN_EXAMPLE_TOKEN": " "})

    registry.register(
        PluginSettingsSpec("secure", keys=("TOKEN",), secret_keys=frozenset({"TOKEN"}))
    )
    with pytest.raises(PluginSettingsError, match="secret://"):
        registry.load({"RONIN_PLUGIN_SECURE_TOKEN": "raw-secret"})


def test_settings_schema_rejects_invalid_metadata() -> None:
    with pytest.raises(PluginSettingsError, match="duplicate"):
        PluginSettingsRegistry().register(PluginSettingsSpec("example", keys=("TOKEN", "TOKEN")))


def test_settings_spec_default_is_python311_compatible_and_isolated() -> None:
    first = PluginSettingsSpec("first")
    second = PluginSettingsSpec("second")

    assert isinstance(first.defaults, MappingProxyType)
    assert first.defaults == {}
    assert first.defaults is not second.defaults
    with pytest.raises(TypeError):
        first.defaults["TOKEN"] = "value"  # type: ignore[index]  # noqa: S105


def test_secret_reference_is_validated_and_not_materialized() -> None:
    ref = SecretReference("secret://vault/token")
    assert ref.uri == "secret://vault/token"
    with pytest.raises(PluginSettingsError, match="secret://"):
        SecretReference("raw-secret")
