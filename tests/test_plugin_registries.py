from __future__ import annotations

import pytest

from studio_core.plugins import (
    CapabilityRegistry,
    ContributionRegistry,
    PermissionRegistry,
    PluginValidationError,
    RouterRegistry,
)


def test_registries_are_separate_and_expose_read_only_copies() -> None:
    capabilities = CapabilityRegistry()
    permissions = PermissionRegistry()
    routers = RouterRegistry(permissions)
    permissions.add("example:read", "example")
    capabilities.add("example", "example")
    routers.add("GET", "/v1/example", "example", lambda **_: {}, permission="example:read")

    capability_items = capabilities.items
    capability_items["tampered"] = "attacker"

    assert "tampered" not in capabilities.items
    assert routers.items[0].plugin_id == "example"


def test_router_registry_requires_owned_permission_and_rejects_collisions() -> None:
    permissions = PermissionRegistry()
    routers = RouterRegistry(permissions)
    permissions.add("example:read", "example")

    with pytest.raises(PluginValidationError, match="not declared"):
        routers.add("GET", "/v1/other", "other", lambda **_: {}, permission="example:read")
    routers.add("GET", "/v1/example", "example", lambda **_: {}, permission="example:read")
    with pytest.raises(PluginValidationError, match="route collision"):
        routers.add("GET", "/v1/example", "example", lambda **_: {}, permission="example:read")


def test_contribution_registry_freezes_all_child_registries() -> None:
    registry = ContributionRegistry()
    registry.add_permission("example:read", "example")
    registry.add_route("GET", "/v1/example", "example", lambda **_: {}, permission="example:read")
    registry.freeze()

    with pytest.raises(PluginValidationError, match="frozen"):
        registry.add_capability("example", "example")
    with pytest.raises(PluginValidationError, match="frozen"):
        registry.add_permission("example:write", "example")
    with pytest.raises(PluginValidationError, match="frozen"):
        registry.add_route(
            "POST",
            "/v1/example",
            "example",
            lambda **_: {},
            permission="example:read",
        )
