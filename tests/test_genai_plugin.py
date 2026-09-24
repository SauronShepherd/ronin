from studio_core.plugins import ContributionRegistry, PluginContext
from studio_genai.plugin import GenAIPlugin


def test_genai_plugin_registers_discovery_surfaces() -> None:
    contributions = ContributionRegistry()
    plugin = GenAIPlugin()
    plugin.register(PluginContext(plugin.manifest.id, contributions, {}))
    assert [(item.method, item.path) for item in contributions.router_registry.items] == [
        ("GET", "/v1/workspaces/{workspace_id}/genai/providers"),
        ("GET", "/v1/workspaces/{workspace_id}/genai/health"),
    ]
    assert {item.id for item in contributions.surface_registry.items} == set(
        plugin.manifest.surface_ids
    )


def test_genai_plugin_fails_closed_without_runtime() -> None:
    plugin = GenAIPlugin()
    assert plugin.providers(workspace_id="ws") == {"status": "not_configured", "items": []}
    assert plugin.health(workspace_id="ws") == {
        "status": "not_configured",
        "provider": "unavailable",
    }
