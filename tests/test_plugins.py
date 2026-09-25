from __future__ import annotations

import pytest
from studio_core.plugins import (
    ContributionRegistry,
    PluginCompatibilityError,
    PluginDependency,
    PluginLoadError,
    PluginManager,
    PluginManifest,
    PluginRecord,
    PluginState,
    PluginValidationError,
    SurfaceContribution,
    SurfaceContributionRegistry,
    SurfaceOption,
    _satisfies_host,
)
from studio_plugin_workspaces import WorkspacesPlugin
from studio_runtime import discover_plugins


def test_plugin_manager_defaults_are_explicit_and_fresh() -> None:
    first = PluginManager()
    second = PluginManager()

    assert first.host_version == "1.0.0"
    assert first.plugin_api == "1.0"
    assert first._records == {}
    assert first._started is False
    assert first._records is not second._records


def test_community_plugin_composes_and_starts() -> None:
    manager = PluginManager(host_version="1.2.0", plugin_api="1.0")
    plan = manager.compose((__import_record(WorkspacesPlugin()),))

    assert plan.contributions.capabilities == {
        "workspaces.read": "com.sauronshepherd.ronin.workspaces",
        "workspaces.write": "com.sauronshepherd.ronin.workspaces",
    }
    assert [(route.method, route.path) for route in plan.contributions.routes] == [
        ("GET", "/v1/workspaces"),
        ("GET", "/v1/workspaces/{workspace_id}"),
        ("POST", "/v1/workspaces"),
        ("PUT", "/v1/workspaces/{workspace_id}"),
        ("POST", "/v1/workspaces/{workspace_id}/archive"),
        ("GET", "/v1/workspaces/{workspace_id}/environments"),
        ("POST", "/v1/workspaces/{workspace_id}/environments"),
        ("GET", "/v1/workspaces/{workspace_id}/environments/{environment_id}"),
        ("PUT", "/v1/workspaces/{workspace_id}/environments/{environment_id}"),
        ("POST", "/v1/workspaces/{workspace_id}/environments/{environment_id}/disable"),
        ("POST", "/v1/workspaces/{workspace_id}/environments/{environment_id}/enable"),
        ("POST", "/v1/workspaces/{workspace_id}/projects"),
        ("GET", "/v1/workspaces/{workspace_id}/projects/{project_id}"),
        ("PUT", "/v1/workspaces/{workspace_id}/projects/{project_id}"),
        ("DELETE", "/v1/workspaces/{workspace_id}/projects/{project_id}"),
        ("GET", "/v1/workspaces/{workspace_id}/projects"),
    ]
    assert [item.id for item in plan.contributions.cli_registry.items] == [
        "environments.create.v1",
        "environments.disable.v1",
        "environments.enable.v1",
        "environments.get.v1",
        "environments.list.v1",
        "environments.replace.v1",
        "projects.create.v1",
        "projects.get.v1",
        "projects.list.v1",
        "workspaces.archive.v1",
        "workspaces.create.v1",
        "workspaces.get.v1",
        "workspaces.list.v1",
        "workspaces.update.v1",
    ]
    assert [item.operation_id for item in plan.contributions.client_operation_registry.items] == [
        "environments.create.v1",
        "environments.disable.v1",
        "environments.enable.v1",
        "environments.get.v1",
        "environments.list.v1",
        "environments.replace.v1",
        "projects.create.v1",
        "projects.get.v1",
        "projects.list.v1",
        "workspaces.archive.v1",
        "workspaces.create.v1",
        "workspaces.get.v1",
        "workspaces.list.v1",
        "workspaces.update.v1",
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


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"id": "Bad.Plugin"}, "invalid plugin id"),
        ({"name": ""}, "incomplete manifest"),
        ({"edition": "enterprise"}, "invalid edition"),
        ({"isolation": "remote"}, "invalid isolation"),
        ({"capabilities": ("same", "same")}, "duplicate capability"),
        ({"permissions": ("same:read", "same:read")}, "duplicate permission"),
        ({"permissions": ("missing-namespace",)}, "permissions must use namespace:name"),
        ({"dependencies": (PluginDependency("com.example.dep"), PluginDependency("com.example.dep"))}, "duplicate dependency"),
        ({"job_types": ("job", "job")}, "duplicate job type"),
    ],
)
def test_manifest_validation_rejects_invalid_contracts(
    changes: dict[str, object], message: str
) -> None:
    manifest = PluginManifest(
        id="com.example.plugin",
        name="Example",
        version="1.0.0",
        plugin_api="1.0",
    )
    updated = {field: getattr(manifest, field) for field in manifest.__dataclass_fields__}
    updated.update(changes)
    with pytest.raises(PluginValidationError, match=message):
        PluginManifest(**updated).validate()


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


@pytest.mark.parametrize(
    "specifier, host, expected",
    [
        ("", "1.0.0", True),
        ("*", "1.0.0", True),
        (">=1,<2", "1.5.0", True),
        (">=2", "1.5.0", False),
        ("<1", "1.0.0", False),
        ("==1.0.0", "1.0.0", True),
        ("==1.0.0", "1.0.1", False),
    ],
)
def test_host_requirement_subset_is_evaluated_fail_closed(
    specifier: str, host: str, expected: bool
) -> None:
    assert _satisfies_host(specifier, host) is expected


def test_host_requirement_rejects_invalid_versions_and_specifiers() -> None:
    with pytest.raises(PluginCompatibilityError, match="invalid host version"):
        _satisfies_host(">=1", "unknown")
    with pytest.raises(PluginCompatibilityError, match="unsupported host requirement"):
        _satisfies_host("~=1.0", "1.0.0")


def test_noncritical_startup_failure_is_degraded_and_manager_starts() -> None:
    plugin = WorkspacesPlugin()
    plugin.startup = lambda: (_ for _ in ()).throw(RuntimeError("optional unavailable"))
    manager = PluginManager()
    plan = manager.compose((__import_record(plugin),))
    result = manager.start(plan)

    assert result[0].state is PluginState.DEGRADED
    assert result[0].error == "optional unavailable"


def test_critical_startup_failure_rolls_back_previous_plugins() -> None:
    class FirstPlugin:
        manifest = PluginManifest("com.example.aaa", "First", "1.0.0", "1.0")
        register = lambda self, context: None
        startup = lambda self: None

    first = FirstPlugin()
    class CriticalPlugin:
        manifest = PluginManifest(
            id="com.example.critical",
            name="Critical",
            version="1.0.0",
            plugin_api="1.0",
            critical=True,
        )
        register = lambda self, context: None
        shutdown = lambda self: None

    second = CriticalPlugin()
    shutdowns: list[str] = []
    first.shutdown = lambda: shutdowns.append("first")
    second.startup = lambda: (_ for _ in ()).throw(RuntimeError("fatal"))
    manager = PluginManager()
    plan = manager.compose((PluginRecord(first.manifest, first, "test"), PluginRecord(second.manifest, second, "test")))

    with pytest.raises(PluginLoadError, match="critical plugin failed to start"):
        manager.start(plan)
    assert shutdowns == ["first"]


def test_manager_rejects_double_start_and_stop_is_reverse_order() -> None:
    class LifecyclePlugin:
        def __init__(self, plugin_id: str) -> None:
            self.manifest = PluginManifest(plugin_id, plugin_id, "1.0.0", "1.0")
        def register(self, context) -> None:
            return None
        def startup(self) -> None:
            return None
        def shutdown(self) -> None:
            return None

    first = LifecyclePlugin("com.example.first")
    second = LifecyclePlugin("com.example.second")
    events: list[str] = []
    first.startup = lambda: events.append("start:first")
    second.startup = lambda: events.append("start:second")
    first.shutdown = lambda: events.append("stop:first")
    second.shutdown = lambda: events.append("stop:second")
    manager = PluginManager()
    plan = manager.compose((PluginRecord(first.manifest, first, "test"), PluginRecord(second.manifest, second, "test")))
    manager.start(plan)

    with pytest.raises(PluginValidationError, match="already started"):
        manager.start(plan)
    manager.stop(plan)
    assert events == ["start:first", "start:second", "stop:second", "stop:first"]


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
    plan = manager.compose((__import_record(plugin),), services={"workspace_service": Service()})
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


def test_surface_contributions_are_sorted_and_collision_safe() -> None:
    registry = SurfaceContributionRegistry()
    registry.add(
        SurfaceContribution(
            id="com.example.z.inspect",
            plugin_id="com.example.z",
            namespace="z",
            command="inspect",
            operation_id="z.inspect.v1",
            capability="z:read",
            permission="z:read",
            options=(SurfaceOption("limit", {"type": "integer"}),),
            path="/v1/z/inspect",
        )
    )
    registry.add(
        SurfaceContribution(
            id="com.example.a.inspect",
            plugin_id="com.example.a",
            namespace="a",
            command="inspect",
            operation_id="a.inspect.v1",
            capability="a:read",
            permission="a:read",
            path="/v1/a/inspect",
        )
    )

    assert [item.id for item in registry.items] == [
        "com.example.a.inspect",
        "com.example.z.inspect",
    ]
    with pytest.raises(PluginValidationError, match="surface command collision"):
        registry.add(
            SurfaceContribution(
                id="com.example.a.other",
                plugin_id="com.example.a",
                namespace="a",
                command="inspect",
                operation_id="a.other.v1",
                capability="a:read",
                permission="a:read",
                path="/v1/a/inspect",
            )
        )


def test_surface_contribution_rejects_duplicate_options() -> None:
    with pytest.raises(PluginValidationError, match="duplicate surface option"):
        SurfaceContribution(
            id="com.example.inspect",
            plugin_id="com.example",
            namespace="example",
            command="inspect",
            operation_id="example.inspect.v1",
            capability="example:read",
            permission="example:read",
            options=(
                SurfaceOption("format", {"type": "string"}),
                SurfaceOption("format", {"type": "string"}),
            ),
            path="/v1/example/inspect",
        ).validate()


def test_surface_requires_owned_capability_and_permission() -> None:
    registry = ContributionRegistry()
    registry.add_capability("example.read", "com.example")
    registry.add_permission("example:read", "com.example")
    contribution = SurfaceContribution(
        id="com.example.inspect",
        plugin_id="com.other",
        namespace="example",
        command="inspect",
        operation_id="example.inspect.v1",
        capability="example.read",
        permission="example:read",
        path="/v1/example/inspect",
    )
    with pytest.raises(PluginValidationError, match="surface capability"):
        registry.add_surface(contribution)


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
