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
    EventSubscriptionRegistry,
    JobRegistry,
    MigrationRegistry,
    PermissionRegistry,
    PluginValidationError,
    SurfaceContribution,
    SurfaceContributionRegistry,
    UiContributionRegistry,
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
