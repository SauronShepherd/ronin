from __future__ import annotations

from studio_core.plugins import PluginManager, PluginRecord
from studio_plugin_workspaces import WorkspacesPlugin
from studio_runtime import PluginHost


def test_plugin_host_resolves_templated_route_parameters() -> None:
    plugin = WorkspacesPlugin()
    manager = PluginManager()
    plan = manager.compose((PluginRecord(plugin.manifest, plugin, "test"),))
    host = PluginHost(manager, plan)

    resolved = host.resolve_route("GET", "/v1/workspaces/ws-1/projects")

    assert resolved is not None
    route, parameters = resolved
    assert route.permission == "workspaces:read"
    assert parameters == {"workspace_id": "ws-1"}
