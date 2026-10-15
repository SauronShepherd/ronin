from __future__ import annotations

from studio_core.plugins import PluginManager, PluginRecord
from studio_plugin_workspaces import WorkspacesPlugin


def test_workspaces_plugin_registers_declarative_ui_manifest() -> None:
    plugin = WorkspacesPlugin()
    plan = PluginManager().compose((PluginRecord(plugin.manifest, plugin, "test"),))

    items = plan.contributions.ui_registry.items

    assert len(items) == 1
    assert items[0].plugin_id == plugin.manifest.id
    assert items[0].manifest["ui_api"] == "1.0"
    assert items[0].manifest["navigation"][0]["permission"] == "workspaces:read"
