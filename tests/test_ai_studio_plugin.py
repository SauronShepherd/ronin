from studio_ai_studio.plugin import AIStudioPlugin
from studio_core.plugins import ContributionRegistry, PluginContext


def test_ai_studio_plugin_registers_workspace_scoped_routes():
    contributions = ContributionRegistry()
    plugin = AIStudioPlugin()
    plugin.register(PluginContext("com.sauronshepherd.ronin.ai-studio", contributions, {}))
    assert [(item.method, item.path) for item in contributions.router_registry.items] == [
        ("GET", "/v1/workspaces/{workspace_id}/ai-studio/models"),
        ("POST", "/v1/workspaces/{workspace_id}/ai-studio/invoke"),
    ]
