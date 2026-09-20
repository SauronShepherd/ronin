"""Contract checks that can be reused by external plugin repositories."""

from __future__ import annotations

from dataclasses import dataclass

from studio_core.plugins import PluginManager, PluginRecord, PluginState, RoninPlugin


@dataclass(frozen=True, slots=True)
class PluginContractReport:
    plugin_id: str
    capabilities: tuple[str, ...]
    permissions: tuple[str, ...]
    routes: tuple[tuple[str, str], ...]
    states: tuple[str, ...]


def validate_plugin(
    plugin: RoninPlugin,
    *,
    host_version: str = "1.0.0",
    plugin_api: str = "1.0",
    services: dict[str, object] | None = None,
) -> PluginContractReport:
    """Compose, start and stop one plugin, raising on contract violations."""
    plugin.manifest.validate()
    manager = PluginManager(host_version=host_version, plugin_api=plugin_api)
    plan = manager.compose((PluginRecord(plugin.manifest, plugin, "testkit"),), services=services)
    states = manager.start(plan)
    try:
        return PluginContractReport(
            plugin_id=plugin.manifest.id,
            capabilities=tuple(sorted(plan.contributions.capabilities)),
            permissions=tuple(sorted(plan.contributions.permissions)),
            routes=tuple(
                (item.method, item.path) for item in plan.contributions.routes
            ),
            states=tuple(item.state.value for item in states),
        )
    finally:
        manager.stop(plan)


def assert_plugin_ready(plugin: RoninPlugin, **kwargs: object) -> PluginContractReport:
    report = validate_plugin(plugin, **kwargs)
    if report.states != (PluginState.READY.value,):
        raise AssertionError(f"plugin did not become ready: {report.states}")
    return report


__all__ = ("PluginContractReport", "assert_plugin_ready", "validate_plugin")
