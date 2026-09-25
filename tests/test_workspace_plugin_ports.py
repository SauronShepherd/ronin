from __future__ import annotations

from studio_core.plugins import PluginManager, PluginRecord
from studio_plugin_workspaces import WorkspacesPlugin
from studio_plugin_workspaces.services import parse_page_query


def test_workspace_plugin_application_uses_port_without_adapter_import() -> None:
    class Workspace:
        id = "workspace-1"
        name = "Workspace 1"
        description = None
        state = "active"

    class Port:
        def list(self):
            return (Workspace(),)

    plugin = WorkspacesPlugin()
    manager = PluginManager()
    plan = manager.compose(
        (PluginRecord(plugin.manifest, plugin, "test"),),
        services={"workspace_service": Port()},
    )
    manager.start(plan)

    assert plugin.list_workspaces() == [
        {
            "id": "workspace-1",
            "name": "Workspace 1",
            "description": None,
            "state": "active",
        }
    ]
    manager.stop(plan)


def test_plugin_project_pagination_is_bounded_and_cursor_versioned() -> None:
    assert parse_page_query(None) == (50, 0)
    assert parse_page_query("limit=10") == (10, 0)
    assert parse_page_query("limit=100&cursor=pp1.MTA") == (100, 10)
