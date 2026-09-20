from __future__ import annotations

import pytest
from studio_core.plugins import (
    PluginCompatibilityError,
    PluginDependency,
    PluginManager,
    PluginManifest,
    PluginState,
    PluginValidationError,
)
from studio_plugin_workspaces import WorkspacesPlugin
from studio_runtime import discover_plugins


def test_community_plugin_composes_and_starts() -> None:
    manager = PluginManager(host_version="1.2.0", plugin_api="1.0")
    plan = manager.compose((__import_record(WorkspacesPlugin()),))

    assert plan.contributions.capabilities == {
        "workspaces.read": "com.sauronshepherd.ronin.workspaces",
        "workspaces.write": "com.sauronshepherd.ronin.workspaces",
    }
    assert [(route.method, route.path) for route in plan.contributions.routes] == [
        ("GET", "/v1/workspaces"),
        ("POST", "/v1/workspaces/{workspace_id}/projects"),
        ("GET", "/v1/workspaces/{workspace_id}/projects/{project_id}"),
        ("PUT", "/v1/workspaces/{workspace_id}/projects/{project_id}"),
        ("DELETE", "/v1/workspaces/{workspace_id}/projects/{project_id}"),
        ("GET", "/v1/workspaces/{workspace_id}/projects"),
    ]
    assert plan.contributions.permissions == {
        "workspaces:read": "com.sauronshepherd.ronin.workspaces",
        "workspaces:write": "com.sauronshepherd.ronin.workspaces",
        "projects:read": "com.sauronshepherd.ronin.workspaces",
        "projects:write": "com.sauronshepherd.ronin.workspaces",
    }
    states = manager.start(plan)
    assert states[0].state is PluginState.READY
    manager.stop(plan)


def test_duplicate_routes_are_rejected() -> None:
    first = __import_record(WorkspacesPlugin())
    second_plugin = WorkspacesPlugin()
    second_plugin.manifest = PluginManifest(
        id="com.example.other",
        name=second_plugin.manifest.name,
        version=second_plugin.manifest.version,
        plugin_api=second_plugin.manifest.plugin_api,
        host_requires=second_plugin.manifest.host_requires,
        capabilities=("other.read",),
        permissions=("other:read",),
    )
    second_plugin.register = lambda context: context.contributions.add_route(
        "GET", "/v1/workspaces", context.plugin_id, lambda: [], permission="other:read"
    )
    second = __import_record(second_plugin)
    with pytest.raises(PluginValidationError, match="route collision"):
        PluginManager().compose((first, second))


def test_route_requires_manifest_permission() -> None:
    plugin = WorkspacesPlugin()
    original_register = plugin.register

    def register_without_permission(context):
        original_register(context)
        context.contributions.add_route(
            "GET", "/v1/invalid", context.plugin_id, lambda: [], permission="other:read"
        )

    plugin.register = register_without_permission
    with pytest.raises(PluginValidationError, match="not declared"):
        PluginManager().compose((__import_record(plugin),))


def test_missing_dependency_is_rejected() -> None:
    plugin = WorkspacesPlugin()
    plugin.manifest = PluginManifest(
        id=plugin.manifest.id,
        name=plugin.manifest.name,
        version=plugin.manifest.version,
        plugin_api=plugin.manifest.plugin_api,
        host_requires=plugin.manifest.host_requires,
        dependencies=(PluginDependency("com.example.missing"),),
    )
    with pytest.raises(PluginValidationError, match="missing plugin dependencies"):
        PluginManager().compose((__import_record(plugin),))


def test_incompatible_api_is_rejected() -> None:
    plugin = WorkspacesPlugin()
    plugin.manifest = PluginManifest(
        id=plugin.manifest.id,
        name=plugin.manifest.name,
        version=plugin.manifest.version,
        plugin_api="2.0",
    )
    with pytest.raises(PluginCompatibilityError, match="plugin API"):
        PluginManager().compose((__import_record(plugin),))


def test_discovery_loads_entry_points_in_deterministic_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EntryPoint:
        def __init__(self, name: str, plugin: WorkspacesPlugin) -> None:
            self.name = name
            self.plugin = plugin

        def load(self):
            return lambda: self.plugin

        def __str__(self) -> str:
            return f"test:{self.name}"

    entries = [EntryPoint("zeta", WorkspacesPlugin()), EntryPoint("alpha", WorkspacesPlugin())]

    class EntryPoints:
        def select(self, *, group: str):
            assert group == "ronin.plugins.v1"
            return entries

    monkeypatch.setattr("studio_runtime.importlib.metadata.entry_points", lambda: EntryPoints())
    records = discover_plugins()

    assert [record.source for record in records] == ["test:alpha", "test:zeta"]


def test_optional_start_failure_is_degraded() -> None:
    plugin = WorkspacesPlugin()
    plugin.startup = lambda: (_ for _ in ()).throw(RuntimeError("dependency unavailable"))
    manager = PluginManager()
    plan = manager.compose((__import_record(plugin),))

    states = manager.start(plan)

    assert states[0].state is PluginState.DEGRADED
    assert states[0].error == "dependency unavailable"


def test_workspace_plugin_delegates_to_injected_service() -> None:
    class Workspace:
        id = "local"
        name = "Local"
        description = "development"
        state = "active"

    class Service:
        def list(self):
            return (Workspace(),)

    plugin = WorkspacesPlugin()
    manager = PluginManager()
    plan = manager.compose(
        (__import_record(plugin),), services={"workspace_service": Service()}
    )
    manager.start(plan)

    assert plugin.list_workspaces() == [
        {
            "id": "local",
            "name": "Local",
            "description": "development",
            "state": "active",
        }
    ]
    manager.stop(plan)


def __import_record(plugin: WorkspacesPlugin, *, plugin_id: str | None = None):
    from studio_core.plugins import PluginRecord

    if plugin_id is not None:
        manifest = plugin.manifest
        plugin.manifest = PluginManifest(
            id=plugin_id,
            name=manifest.name,
            version=manifest.version,
            plugin_api=manifest.plugin_api,
            host_requires=manifest.host_requires,
            edition=manifest.edition,
            capabilities=manifest.capabilities,
            permissions=manifest.permissions,
        )
    return PluginRecord(plugin.manifest, plugin, "test")
