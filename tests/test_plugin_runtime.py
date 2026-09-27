from __future__ import annotations

from studio_core.plugins import PluginManager, PluginRecord
from studio_plugin_workspaces import WorkspacesPlugin
from studio_runtime import PluginHost


def test_plugin_host_starts_and_reports_diagnostics() -> None:
    plugin = WorkspacesPlugin()
    manager = PluginManager()
    plan = manager.compose((PluginRecord(plugin.manifest, plugin, "test"),))
    host = PluginHost(manager, plan)

    states = host.start()

    assert states[0].manifest.id == "com.sauronshepherd.ronin.workspaces"
    assert host.diagnostics()[0]["state"] == "ready"
    host.stop()
    assert host.diagnostics()[0]["state"] == "stopped"


def test_plugin_host_exposes_composition_surface_diagnostics() -> None:
    plugin = WorkspacesPlugin()
    manager = PluginManager()
    plan = manager.compose((PluginRecord(plugin.manifest, plugin, "test"),))
    host = PluginHost(manager, plan)

    diagnostics = host.contribution_diagnostics()

    assert diagnostics["capabilities"]["workspaces.read"] == plugin.manifest.id
    assert diagnostics["permissions"]["projects:write"] == plugin.manifest.id
    assert any(item["path"] == "/v1/workspaces" for item in diagnostics["routes"])
    assert diagnostics["jobs"] == []
    assert diagnostics["settings"] == {"values": {}, "reloadable": {}}
