from __future__ import annotations

from dataclasses import replace

import pytest
from studio_core.plugins import (
    CapabilityRegistry,
    ContributionRegistry,
    EventSubscriptionRegistry,
    JobRegistry,
    MigrationRegistry,
    PermissionRegistry,
    PluginCompatibilityError,
    PluginManager,
    PluginManifest,
    PluginRecord,
    PluginState,
    PluginValidationError,
    RouterRegistry,
    SurfaceContribution,
    SurfaceContributionRegistry,
    SurfaceOption,
    UiContributionRegistry,
    _satisfies_host,
)


def _surface(**changes: object) -> SurfaceContribution:
    base = SurfaceContribution(
        id="example.inspect",
        plugin_id="example",
        namespace="example",
        command="inspect",
        operation_id="example.inspect.v1",
        capability="example.read",
        permission="example:read",
        path="/v1/example/inspect",
    )
    return replace(base, **changes)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", "", "identifiers are required"),
        ("plugin_id", "", "identifiers are required"),
        ("operation_id", "", "identifiers are required"),
        ("namespace", " example", "invalid surface namespace"),
        ("command", "inspect ", "invalid surface command"),
        ("capability", "", "invalid surface capability"),
        ("permission", "example read", "invalid surface permission"),
        ("transport", "tcp", "invalid surface transport"),
        ("path", "/api/v2/example", "versioned API path"),
        ("path", "/v1/example/inspect now", "versioned API path"),
        ("method", "OPTIONS", "invalid HTTP surface method"),
        ("options", (SurfaceOption("--format", {}),), "invalid surface option"),
    ],
)
def test_surface_validation_rejects_each_boundary(field: str, value: object, message: str) -> None:
    with pytest.raises(PluginValidationError, match=message):
        _surface(**{field: value}).validate()


@pytest.mark.parametrize("transport", ["worker", "in_process"])
@pytest.mark.parametrize("path", ["", "not-a-path", "/v2/example"])
def test_non_http_surfaces_do_not_require_http_paths(transport: str, path: str) -> None:
    _surface(transport=transport, path=path).validate()


@pytest.mark.parametrize("method", ["GET", "get", "POST", "PUT", "PATCH", "DELETE"])
def test_surface_validation_accepts_supported_methods(method: str) -> None:
    _surface(method=method).validate()


def test_surface_registry_rejects_operation_collision_independently_of_id() -> None:
    registry = SurfaceContributionRegistry()
    registry.add(_surface())
    with pytest.raises(PluginValidationError, match="surface operation collision"):
        registry.add(_surface(id="example.other", command="other"))


def test_surface_registry_rejects_mutation_after_freeze() -> None:
    registry = SurfaceContributionRegistry()
    registry.freeze()
    registry.freeze()
    with pytest.raises(PluginValidationError, match="plugin registry is frozen"):
        registry.add(_surface())


def test_frozen_registry_diagnostic_is_stable() -> None:
    registry = CapabilityRegistry()
    registry.freeze()
    with pytest.raises(PluginValidationError) as error:
        registry.add("example.read", "example")
    assert str(error.value) == "plugin registry is frozen"


@pytest.mark.parametrize(
    "registry",
    [
        CapabilityRegistry(),
        PermissionRegistry(),
        JobRegistry(),
        EventSubscriptionRegistry(),
        MigrationRegistry(),
        UiContributionRegistry(),
    ],
)
def test_each_contribution_registry_is_frozen_and_freeze_is_idempotent(registry: object) -> None:
    registry.freeze()  # type: ignore[attr-defined]
    registry.freeze()  # type: ignore[attr-defined]
    if isinstance(registry, CapabilityRegistry):
        with pytest.raises(PluginValidationError, match="plugin registry is frozen"):
            registry.add("cap", "plugin")
    elif isinstance(registry, PermissionRegistry):
        with pytest.raises(PluginValidationError, match="plugin registry is frozen"):
            registry.add("plugin:read", "plugin")
    elif isinstance(registry, JobRegistry):
        with pytest.raises(PluginValidationError, match="plugin registry is frozen"):
            registry.add("job", "plugin", object())
    elif isinstance(registry, EventSubscriptionRegistry):
        with pytest.raises(PluginValidationError, match="plugin registry is frozen"):
            registry.add("event", "plugin", object())
    elif isinstance(registry, MigrationRegistry):
        with pytest.raises(PluginValidationError, match="plugin registry is frozen"):
            registry.add("migration", "plugin")
    else:
        with pytest.raises(PluginValidationError, match="plugin registry is frozen"):
            registry.add("plugin", {})


def test_capability_and_permission_registries_are_idempotent_for_same_owner() -> None:
    capabilities = CapabilityRegistry()
    capabilities.add("example.read", "example")
    capabilities.add("example.read", "example")
    assert capabilities.items == {"example.read": "example"}
    with pytest.raises(PluginValidationError, match="already provided"):
        capabilities.add("example.read", "other")

    permissions = PermissionRegistry()
    permissions.add("example:read", "example")
    permissions.add("example:read", "example")
    assert permissions.items == {"example:read": "example"}
    with pytest.raises(PluginValidationError, match="already owned"):
        permissions.add("example:read", "other")


def test_job_event_and_migration_registries_enforce_their_distinct_collision_keys() -> None:
    jobs = JobRegistry()
    handler = object()
    jobs.add("run", "example", handler)
    assert jobs.items == (type(jobs.items[0])("run", "example", handler),)
    with pytest.raises(PluginValidationError, match="job type collision"):
        jobs.add("run", "other", object())

    events = EventSubscriptionRegistry()
    events.add("run.completed", "example", handler)
    events.add("run.completed", "example", object())
    assert len(events.items) == 2
    assert events.items[0].event_type == "run.completed"
    assert events.items[0].plugin_id == "example"
    assert events.items[0].handler is handler
    with pytest.raises(PluginValidationError, match="event subscription collision"):
        events.add("run.completed", "example", handler)

    migrations = MigrationRegistry()
    migrations.add("v1", "example")
    assert migrations.items[0].migration_id == "v1"
    assert migrations.items[0].plugin_id == "example"
    with pytest.raises(PluginValidationError, match="migration collision"):
        migrations.add("v1", "other")


def test_owner_registries_preserve_first_owner_and_idempotent_values() -> None:
    capabilities = CapabilityRegistry()
    capabilities.add("example.read", "example")
    assert capabilities.items["example.read"] == "example"
    capabilities.add("example.read", "example")
    assert capabilities.items == {"example.read": "example"}

    permissions = PermissionRegistry()
    permissions.add("example:read", "example")
    assert permissions.items["example:read"] == "example"
    permissions.add("example:read", "example")
    assert permissions.owns("example:read", "example")


def test_surface_registry_preserves_command_and_operation_indexes() -> None:
    registry = SurfaceContributionRegistry()
    contribution = _surface()
    registry.add(contribution)
    assert registry.items == (contribution,)
    with pytest.raises(PluginValidationError) as command_error:
        registry.add(_surface(id="example.other", command="inspect-other"))
    assert str(command_error.value) == "surface operation collision: example.inspect.v1"


def test_router_registry_normalizes_methods_but_keeps_paths_exact() -> None:
    permissions = PermissionRegistry()
    permissions.add("example:read", "example")
    router = RouterRegistry(permissions)
    handler = object()
    router.add("get", "/v1/items", "example", handler, permission="example:read")
    assert router.items[0].method == "GET"
    with pytest.raises(PluginValidationError, match="route collision"):
        router.add("GET", "/v1/items", "example", object(), permission="example:read")
    with pytest.raises(PluginValidationError, match="route permission"):
        router.add("POST", "/v1/items", "other", object(), permission="example:read")


def test_contribution_registry_projects_all_owned_contributions_and_ui_requirement() -> None:
    registry = ContributionRegistry()
    handler = object()
    registry.add_job("job", "example", handler)
    registry.add_event_subscription("event", "example", handler)
    registry.add_migration("migration", "example")
    registry.add_ui("example", {"entry": "ui"})
    manifest = PluginManifest(
        "example",
        "Example",
        "1.0.0",
        "1.0",
        job_types=("job",),
        event_types=("event",),
        migration_ids=("migration",),
        ui_entry="package:app",
    )
    registry.validate_manifest(manifest)


@pytest.mark.parametrize(
    ("field", "contribution", "message"),
    [
        ("event_types", "event", "undeclared event"),
        ("migration_ids", "migration", "undeclared migration"),
        ("surface_ids", "example.inspect", "undeclared surface"),
    ],
)
def test_manifest_validation_rejects_undeclared_contribution(
    field: str, contribution: str, message: str
) -> None:
    registry = ContributionRegistry()
    if field == "event_types":
        registry.add_event_subscription(contribution, "example", object())
    elif field == "migration_ids":
        registry.add_migration(contribution, "example")
    else:
        registry.add_capability("example.read", "example")
        registry.add_permission("example:read", "example")
        registry.add_surface(_surface())
    with pytest.raises(PluginValidationError, match=message):
        registry.validate_manifest(PluginManifest("example", "Example", "1.0.0", "1.0"))


def test_manifest_validation_requires_ui_entry_for_ui_contribution() -> None:
    registry = ContributionRegistry()
    registry.add_ui("example", {})
    with pytest.raises(PluginValidationError, match="UI contribution requires ui_entry"):
        registry.validate_manifest(PluginManifest("example", "Example", "1.0.0", "1.0"))


@pytest.mark.parametrize(
    ("specifier", "host", "expected"),
    [
        (">=1", "1.0.0", True),
        (">=2", "2.0.0", True),
        ("<2", "1.9.9", True),
        ("<2", "2.0.0", False),
        ("==1.0.0", "1.0.0", True),
        ("==1.0.0", "1.0.1", False),
        (" >=1 , <2 ", "1.5.0", True),
    ],
)
def test_host_requirement_boundaries(specifier: str, host: str, expected: bool) -> None:
    assert _satisfies_host(specifier, host) is expected


def test_host_requirement_rejects_numeric_but_unsupported_components() -> None:
    with pytest.raises(PluginCompatibilityError, match="unsupported host requirement"):
        _satisfies_host("=1", "1.0.0")


def test_compose_uses_empty_context_defaults_and_preserves_record_metadata() -> None:
    captured: list[tuple[dict[str, object], dict[str, object]]] = []

    class Plugin:
        manifest = PluginManifest("example", "Example", "1.0.0", "1.0")

        def register(self, context) -> None:
            captured.append((dict(context.services), dict(context.settings)))

        def startup(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

    original = PluginRecord(
        Plugin.manifest,
        Plugin(),
        "wheel:example",
        distribution="example",
        distribution_version="1.2.3",
        artifact_hash="sha256:abc",
    )
    plan = PluginManager().compose((original,))
    assert captured == [({}, {})]
    record = plan.records[0]
    assert record.state is PluginState.REGISTERED
    assert record.source == original.source
    assert record.distribution == original.distribution
    assert record.distribution_version == original.distribution_version
    assert record.artifact_hash == original.artifact_hash


def test_noncritical_start_failure_preserves_metadata_and_marks_degraded() -> None:
    class Plugin:
        manifest = PluginManifest("example", "Example", "1.0.0", "1.0")

        def register(self, _context) -> None:
            return None

        def startup(self) -> None:
            raise RuntimeError("unavailable")

        def shutdown(self) -> None:
            return None

    source = PluginRecord(
        Plugin.manifest,
        Plugin(),
        "wheel:example",
        distribution="example",
        distribution_version="1.2.3",
        artifact_hash="sha256:abc",
    )
    manager = PluginManager()
    result = manager.start(manager.compose((source,)))
    assert result[0].state is PluginState.DEGRADED
    assert result[0].error == "unavailable"
    assert result[0].source == source.source
    assert result[0].distribution_version == source.distribution_version


def test_stop_resets_started_state_when_all_shutdowns_succeed() -> None:
    class Plugin:
        manifest = PluginManifest("example", "Example", "1.0.0", "1.0")

        def register(self, _context) -> None:
            return None

        def startup(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

    manager = PluginManager()
    plan = manager.compose((PluginRecord(Plugin.manifest, Plugin(), "test"),))
    manager.start(plan)
    manager.stop(plan)
    assert manager._started is False
    assert manager.start(plan)[0].state is PluginState.READY
