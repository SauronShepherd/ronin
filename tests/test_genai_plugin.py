from studio_core.plugins import ContributionRegistry, PluginContext
from studio_genai.plugin import GenAIPlugin


def test_genai_plugin_registers_discovery_surfaces() -> None:
    contributions = ContributionRegistry()
    plugin = GenAIPlugin()
    plugin.register(PluginContext(plugin.manifest.id, contributions, {}))
    assert [(item.method, item.path) for item in contributions.router_registry.items] == [
        ("GET", "/v1/workspaces/{workspace_id}/genai/providers"),
        ("GET", "/v1/workspaces/{workspace_id}/genai/health"),
        ("GET", "/v1/workspaces/{workspace_id}/genai/prompts"),
        ("PUT", "/v1/workspaces/{workspace_id}/genai/prompts/{prompt_id}/{version}"),
        ("GET", "/v1/workspaces/{workspace_id}/genai/indexes"),
        ("DELETE", "/v1/workspaces/{workspace_id}/genai/indexes/{index_id}"),
        ("POST", "/v1/workspaces/{workspace_id}/genai/indexes/{index_id}/query"),
        ("POST", "/v1/workspaces/{workspace_id}/genai/indexes/{index_id}/build"),
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
    assert plugin.prompts(workspace_id="ws") == {"status": "not_configured", "items": []}
    assert plugin.put_prompt(workspace_id="ws", prompt_id="p", version="1", body={}) == {
        "status": "not_configured"
    }
    assert plugin.indexes(workspace_id="ws") == {"status": "not_configured", "items": []}
    assert plugin.delete_index(workspace_id="ws", index_id="idx") == {
        "status": "not_configured",
        "deleted": False,
    }
    assert plugin.search_index(workspace_id="ws", index_id="idx", body={}) == {
        "status": "not_configured",
        "items": [],
    }
    assert plugin.build_index(workspace_id="ws", index_id="idx", body={}) == {
        "status": "not_configured"
    }
