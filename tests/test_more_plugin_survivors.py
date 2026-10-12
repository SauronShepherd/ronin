"""Contract matrix for registry ownership and plugin lifecycle boundaries."""

from __future__ import annotations

import pytest
from studio_core.plugins import (
    CapabilityRegistry,
    ContributionRegistry,
    EventSubscriptionRegistry,
    JobRegistry,
    MigrationRegistry,
    PermissionRegistry,
    PluginCompatibilityError,
    PluginLoadError,
    PluginManager,
    PluginManifest,
    PluginRecord,
    PluginValidationError,
    RouterRegistry,
    _satisfies_host,
)


def test_capability_and_permission_registries_reject_takeover_after_replay() -> None:
    capabilities = CapabilityRegistry()
    capabilities.add("data.read", "one")
    capabilities.add("data.read", "one")
    assert capabilities.items == {"data.read": "one"}
    with pytest.raises(PluginValidationError, match="already provided"):
        capabilities.add("data.read", "two")

    permissions = PermissionRegistry()
    permissions.add("data:read", "one")
    permissions.add("data:read", "one")
    assert permissions.owns("data:read", "one")
    assert not permissions.owns("data:read", "two")
    with pytest.raises(PluginValidationError, match="already owned"):
        permissions.add("data:read", "two")


def test_registry_outputs_are_deterministic_and_router_normalizes_methods() -> None:
    jobs = JobRegistry()
    jobs.add("z", "plugin", object())
    jobs.add("a", "plugin", object())
    assert tuple(item.job_type for item in jobs.items) == ("a", "z")
    events = EventSubscriptionRegistry()
    first = object()
    events.add("z", "plugin", first)
    events.add("a", "plugin", object())
    assert tuple(item.event_type for item in events.items) == ("a", "z")
    with pytest.raises(PluginValidationError, match="collision"):
        events.add("z", "plugin", first)
    migrations = MigrationRegistry()
    migrations.add("z", "plugin")
    migrations.add("a", "plugin")
    assert tuple(item.migration_id for item in migrations.items) == ("a", "z")

    permissions = PermissionRegistry()
    permissions.add("plugin:read", "plugin")
    router = RouterRegistry(permissions)
    router.add("get", "/v1/items", "plugin", object(), permission="plugin:read")
    assert router.items[0].method == "GET"
    with pytest.raises(PluginValidationError, match="collision"):
        router.add("GET", "/v1/items", "plugin", object(), permission="plugin:read")


@pytest.mark.parametrize(
    ("specifier", "host", "expected"),
    [
        ("", "1.0.0", True),
        ("*", "1.0.0", True),
        (">=1,<2", "1.5.0", True),
        (">=2", "1.5.0", False),
        ("<1", "1.5.0", False),
        ("==1.0.0", "1.0.0", True),
    ],
)
def test_host_requirement_contract_covers_empty_wildcard_and_comparison_boundaries(
    specifier: str, host: str, expected: bool
) -> None:
    assert _satisfies_host(specifier, host) is expected


@pytest.mark.parametrize("specifier", ["~=1.0", "=>1", "abc", ">=x"])
def test_host_requirement_rejects_unsupported_or_non_numeric_components(specifier: str) -> None:
    with pytest.raises(PluginCompatibilityError):
        _satisfies_host(specifier, "1.0.0")


def test_contribution_registry_enforces_surface_ownership_only_when_owners_exist() -> None:
    registry = ContributionRegistry()
    # A standalone registry may accept a surface before capabilities are declared.
    from studio_core.plugins import SurfaceContribution

    surface = SurfaceContribution(
        id="plugin.inspect",
        plugin_id="plugin",
        namespace="plugin",
        command="inspect",
        operation_id="plugin.inspect.v1",
        capability="plugin.read",
        permission="plugin:read",
        path="/v1/plugin/inspect",
    )
    with pytest.raises(PluginValidationError, match="permission"):
        registry.add_surface(surface)
    registry.add_permission("plugin:read", "plugin")
    registry.add_surface(surface)
    assert registry.routes == ()
    assert registry.surface_registry.items[0].id == "plugin.inspect"


def test_plugin_manager_rejects_duplicate_compose_and_prevents_started_reentry() -> None:
    class Plugin:
        manifest = PluginManifest("plugin", "Plugin", "1.0.0", "1.0")

        def register(self, _context) -> None:
            return None

        def startup(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

    manager = PluginManager()
    plan = manager.compose((PluginRecord(Plugin.manifest, Plugin(), "test"),))
    manager.start(plan)
    with pytest.raises(PluginValidationError, match="already started"):
        manager.start(plan)


def test_critical_plugin_start_failure_rolls_back_previous_plugins() -> None:
    events: list[str] = []

    class Healthy:
        manifest = PluginManifest("healthy", "Healthy", "1.0.0", "1.0")

        def register(self, _context) -> None:
            return None

        def startup(self) -> None:
            events.append("healthy-start")

        def shutdown(self) -> None:
            events.append("healthy-stop")

    class Broken:
        manifest = PluginManifest("broken", "Broken", "1.0.0", "1.0", critical=True)

        def register(self, _context) -> None:
            return None

        def startup(self) -> None:
            events.append("broken-start")
            raise RuntimeError("broken")

        def shutdown(self) -> None:
            events.append("broken-stop")

    manager = PluginManager()
    plan = manager.compose(
        (
            PluginRecord(Healthy.manifest, Healthy(), "test"),
            PluginRecord(Broken.manifest, Broken(), "test"),
        )
    )
    with pytest.raises(PluginLoadError, match="critical plugin failed to start"):
        manager.start(plan)
    assert events == ["healthy-start", "broken-start", "healthy-stop"]
