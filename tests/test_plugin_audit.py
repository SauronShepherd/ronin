from __future__ import annotations

from studio_core.plugins import PluginManager, PluginRecord
from studio_plugin_workspaces import WorkspacesPlugin
from studio_runtime import PluginHost


def test_plugin_route_invocation_emits_sanitized_audit_event() -> None:
    events: list[dict[str, object]] = []
    plugin = WorkspacesPlugin()
    manager = PluginManager()
    plan = manager.compose((PluginRecord(plugin.manifest, plugin, "test"),))
    host = PluginHost(manager, plan, audit=events.append)
    manager.start(plan)

    result = host.invoke_route("GET", "/v1/workspaces/ws-1/projects", query="limit=10")

    assert result == {"items": [], "next_cursor": None}
    assert events == [
        {
            "event": "plugin.route.invoked",
            "plugin_id": "com.sauronshepherd.ronin.workspaces",
            "method": "GET",
            "path": "/v1/workspaces/{workspace_id}/projects",
            "permission": "workspaces:read",
            "parameter_names": ("workspace_id",),
            "result": "success",
        }
    ]
