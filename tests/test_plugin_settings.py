from __future__ import annotations

import pytest
from studio_runtime import (
    PluginSettingsError,
    PluginSettingsRegistry,
    PluginSettingsSpec,
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
            "RONIN_PLUGIN_EXAMPLE_TOKEN": "secret",
        }
    )

    assert registry.get("example")["ENDPOINT"] == "https://example"
    assert registry.redacted()["example"]["TOKEN"] == "[REDACTED]"  # noqa: S105
    assert registry.get("example")["TIMEOUT"] == 30
    assert registry.reloadable()["example"] == ("TIMEOUT",)


def test_settings_reject_unknown_keys_and_empty_values() -> None:
    registry = PluginSettingsRegistry()
    registry.register(PluginSettingsSpec("example", keys=("TOKEN",)))

    with pytest.raises(PluginSettingsError, match="unknown setting"):
        registry.load({"RONIN_PLUGIN_EXAMPLE_UNKNOWN": "value"})
    with pytest.raises(PluginSettingsError, match="must not be empty"):
        registry.load({"RONIN_PLUGIN_EXAMPLE_TOKEN": " "})


def test_settings_schema_rejects_invalid_metadata() -> None:
    with pytest.raises(PluginSettingsError, match="duplicate"):
        PluginSettingsRegistry().register(
            PluginSettingsSpec("example", keys=("TOKEN", "TOKEN"))
        )
