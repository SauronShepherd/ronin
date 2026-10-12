"""Boundary decisions left weak by the recorded mutation survivor report."""

from __future__ import annotations

import pytest
from studio_core.grants import (
    Grant,
    GrantSet,
    Requirement,
    ResourceScope,
    parse_legacy_permission,
)
from studio_core.plugins import (
    CapabilityRegistry,
    ContributionRegistry,
    EventSubscriptionRegistry,
    JobRegistry,
    MigrationRegistry,
    PermissionRegistry,
    PluginCompatibilityError,
    PluginDependency,
    PluginManager,
    PluginManifest,
    PluginRecord,
    PluginValidationError,
    RouterRegistry,
    SurfaceContribution,
    SurfaceContributionRegistry,
    UiContributionRegistry,
    _satisfies_host,
)


def test_grant_matching_distinguishes_kind_identifier_and_wildcards() -> None:
    requirement = Requirement("read", ResourceScope("project", "p-1"))
    assert (
        GrantSet((Grant(frozenset({"read"}), ResourceScope("job", "p-1")),))
        .permits(requirement)
        .reason
        == "no_matching_grant"
    )
    assert (
        GrantSet((Grant(frozenset({"read"}), ResourceScope("project", "p-2")),))
        .permits(requirement)
        .reason
        == "no_matching_grant"
    )
    assert (
        GrantSet((Grant(frozenset({"read"}), ResourceScope("project", None)),))
        .permits(requirement)
        .reason
        == "allowed"
    )
    assert (
        GrantSet((Grant(frozenset({"read"}), ResourceScope("*", None)),))
        .permits(requirement)
        .reason
        == "allowed"
    )


def test_grant_matching_prefers_exact_scope_over_wildcard_and_rejects_constraints() -> None:
    requirement = Requirement("read", ResourceScope("project", "p-1"))
    exact = Grant(frozenset({"read"}), ResourceScope("project", "p-1"))
    wildcard = Grant(frozenset({"read"}), ResourceScope("project", None))
    constrained = Grant(frozenset({"read"}), ResourceScope("project", "p-1"), {"tenant": "x"})
    assert GrantSet((wildcard, exact)).permits(requirement).matched_grant == exact
    assert GrantSet((constrained,)).permits(requirement).reason == "unsupported_constraints"


def test_grant_wire_payloads_preserve_versions_shapes_and_canonical_order() -> None:
    requirement = Requirement("write", ResourceScope("project", "p-1"))
    grant = Grant(frozenset({"write", "read"}), requirement.resource)
    grants = GrantSet((grant,))
    assert Requirement.from_payload(requirement.to_payload()) == requirement
    assert Grant.from_payload(grant.to_payload()) == grant
    assert GrantSet.from_payload(grants.to_payload()) == grants
    assert GrantSet.from_json(grants.to_json()) == grants
    assert parse_legacy_permission("ronin:v1:write:project:p-1") == requirement


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"version": True, "action": "read", "resource": {}}, "field types"),
        ({"version": 1, "action": "read", "resource": {"kind": "project"}}, "exactly"),
        ({"version": 1, "action": "read", "resource": None}, "exactly"),
        (
            {"version": 1, "action": "read", "resource": {"kind": "project", "identifier": 1}},
            "field types",
        ),
    ],
)
def test_requirement_payload_parser_rejects_noncanonical_shapes(
    payload: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        Requirement.from_payload(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"version": 1, "actions": "read", "resource": {"kind": "project", "identifier": "p"}},
        {"version": 1, "actions": ["read"], "resource": {"kind": "project"}},
        {
            "version": 1,
            "actions": ["read"],
            "resource": {"kind": "project", "identifier": "p"},
            "constraints": [],
        },
        {
            "version": 1,
            "actions": ["read"],
            "resource": {"kind": "project", "identifier": "p"},
            "constraints": {"tenant": 1},
        },
    ],
)
def test_grant_payload_parser_rejects_noncanonical_shapes(payload: object) -> None:
    with pytest.raises(ValueError, match="."):
        Grant.from_payload(payload)


@pytest.mark.parametrize(
    ("registry_type", "add", "message"),
    [
        (CapabilityRegistry, lambda registry: registry.add("cap", "other"), "already provided"),
        (
            PermissionRegistry,
            lambda registry: registry.add("example:read", "other"),
            "already owned",
        ),
        (
            JobRegistry,
            lambda registry: registry.add("job", "plugin", lambda: None),
            "job type collision",
        ),
        (
            MigrationRegistry,
            lambda registry: registry.add("migration", "plugin"),
            "migration collision",
        ),
        (
            UiContributionRegistry,
            lambda registry: registry.add("plugin", {"entry": "ui"}),
            "UI contribution collision",
        ),
    ],
)
def test_plugin_registries_reject_cross_owner_or_duplicate_entries(
    registry_type, add, message: str
) -> None:
    registry = registry_type()
    if registry_type is CapabilityRegistry:
        registry.add("cap", "owner")
    elif registry_type is PermissionRegistry:
        registry.add("example:read", "owner")
    elif registry_type is JobRegistry:
        registry.add("job", "owner", lambda: None)
    elif registry_type is MigrationRegistry:
        registry.add("migration", "owner")
    else:
        registry.add("plugin", {"entry": "ui"})
    with pytest.raises(PluginValidationError, match=message):
        add(registry)


def test_event_and_surface_registries_have_deterministic_collision_boundaries() -> None:
    events = EventSubscriptionRegistry()

    def handler() -> None:
        return None

    events.add("run.completed", "plugin", handler)
    with pytest.raises(PluginValidationError, match="event subscription collision"):
        events.add("run.completed", "plugin", handler)

    surfaces = SurfaceContributionRegistry()
    first = SurfaceContribution(
        id="plugin.run",
        plugin_id="plugin",
        namespace="plugin",
        command="run",
        operation_id="plugin.run.v1",
        capability="plugin.run",
        permission="plugin:run",
        transport="http",
        method="POST",
        path="/v1/plugin/run",
    )
    surfaces.add(first)
    with pytest.raises(PluginValidationError, match="surface contribution collision"):
        surfaces.add(first)


def test_registry_ownership_normalization_and_freeze_boundaries() -> None:
    capabilities = CapabilityRegistry()
    capabilities.add("cap", "owner")
    capabilities.add("cap", "owner")
    assert capabilities.items == {"cap": "owner"}

    permissions = PermissionRegistry()
    permissions.add("example:read", "owner")
    router = RouterRegistry(permissions)

    def handler() -> None:
        return None

    router.add("get", "/v1/example", "owner", handler, permission="example:read")
    assert router.items[0].method == "GET"
    with pytest.raises(PluginValidationError, match="route collision"):
        router.add("GET", "/v1/example", "owner", handler, permission="example:read")
    with pytest.raises(PluginValidationError, match="not declared"):
        router.add("POST", "/v1/other", "owner", handler, permission="example:write")

    registry = ContributionRegistry()
    registry.freeze()
    with pytest.raises(PluginValidationError, match="frozen"):
        registry.add_capability("late", "owner")


def test_host_requirement_boundaries_are_strict_and_fail_closed() -> None:
    assert _satisfies_host(">=1,<2,==1.5.0", "1.5.0") is True
    assert _satisfies_host(">=1,<2", "2.0.0") is False
    with pytest.raises((PluginCompatibilityError, ValueError)):
        _satisfies_host(">=x", "1.0.0")
    with pytest.raises(PluginCompatibilityError, match="unsupported"):
        _satisfies_host("~=1.0", "1.0.0")


def test_compose_passes_services_settings_and_orders_dependencies() -> None:
    seen: list[tuple[str, dict[str, object], dict[str, object]]] = []

    class Plugin:
        def __init__(self, manifest: PluginManifest) -> None:
            self.manifest = manifest

        def register(self, context) -> None:
            seen.append((context.plugin_id, dict(context.services), dict(context.settings)))

        def startup(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

    dependency_manifest = PluginManifest("example.base", "Base", "1.0.0", "1.0")
    dependent_manifest = PluginManifest(
        "example.app",
        "App",
        "1.0.0",
        "1.0",
        dependencies=(PluginDependency("example.base"),),
    )
    dependency = Plugin(dependency_manifest)
    dependent = Plugin(dependent_manifest)
    plan = PluginManager().compose(
        (
            PluginRecord(dependent_manifest, dependent, "test"),
            PluginRecord(dependency_manifest, dependency, "test"),
        ),
        services={"clock": object()},
        settings={"example.app": {"mode": "safe"}},
    )
    assert [record.manifest.id for record in plan.records] == ["example.base", "example.app"]
    assert [item[0] for item in seen] == ["example.base", "example.app"]
    assert seen[1][2] == {"mode": "safe"}


def test_compose_rejects_missing_dependency_cycle_and_second_composition() -> None:
    def make_record(
        plugin_id: str, dependencies: tuple[PluginDependency, ...] = ()
    ) -> PluginRecord:
        manifest = PluginManifest(
            plugin_id,
            plugin_id,
            "1.0.0",
            "1.0",
            dependencies=dependencies,
        )

        class Plugin:
            def register(self, _context) -> None:
                return None

            def startup(self) -> None:
                return None

            def shutdown(self) -> None:
                return None

        plugin = Plugin()
        plugin.manifest = manifest
        return PluginRecord(manifest, plugin, "test")

    with pytest.raises(PluginValidationError, match="missing plugin dependencies"):
        PluginManager().compose((make_record("example.app", (PluginDependency("example.base"),)),))

    cycle = (
        make_record("example.a", (PluginDependency("example.b"),)),
        make_record("example.b", (PluginDependency("example.a"),)),
    )
    with pytest.raises(PluginValidationError, match="dependency cycle"):
        PluginManager().compose(cycle)

    manager = PluginManager()
    manager.compose((make_record("example.one"),))
    with pytest.raises(PluginValidationError, match="already been composed"):
        manager.compose((make_record("example.two"),))
