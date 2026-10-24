from __future__ import annotations

from dataclasses import replace

import pytest
from studio_core.graph_executor import LocalGraphQueryExecutor
from studio_core.ontology import KnowledgeGraph
from studio_core.openlineage_transport import validate_openlineage_event
from studio_core.plugin_events import InMemoryInbox, InMemoryOutbox, PluginEventError, new_event
from studio_core.plugins import (
    CapabilityRegistry,
    EventSubscriptionRegistry,
    JobRegistry,
    MigrationRegistry,
    PermissionRegistry,
    PluginContext,
    PluginDependency,
    PluginManager,
    PluginManifest,
    PluginRecord,
    PluginValidationError,
    RouterRegistry,
    SurfaceContribution,
    SurfaceContributionRegistry,
    UiContributionRegistry,
)
from studio_core.rql import parse_rql


def test_registries_freeze_every_mutation_surface() -> None:
    registries = [
        CapabilityRegistry(),
        PermissionRegistry(),
        JobRegistry(),
        EventSubscriptionRegistry(),
        MigrationRegistry(),
        UiContributionRegistry(),
        SurfaceContributionRegistry(),
    ]
    for registry in registries:
        registry.freeze()
    with pytest.raises(PluginValidationError, match="frozen"):
        registries[0].add("read", "plugin")
    with pytest.raises(PluginValidationError, match="frozen"):
        registries[1].add("read:read", "plugin")
    with pytest.raises(PluginValidationError, match="frozen"):
        registries[2].add("job", "plugin", lambda: None)
    with pytest.raises(PluginValidationError, match="frozen"):
        registries[3].add("event", "plugin", lambda: None)
    with pytest.raises(PluginValidationError, match="frozen"):
        registries[4].add("migration", "plugin")
    with pytest.raises(PluginValidationError, match="frozen"):
        registries[5].add("plugin", {})
    contribution = SurfaceContribution(
        "plugin.inspect",
        "plugin",
        "plugin",
        "inspect",
        "plugin.inspect.v1",
        "plugin.read",
        "plugin:read",
        path="/v1/plugin/inspect",
    )
    with pytest.raises(PluginValidationError, match="frozen"):
        registries[6].add(contribution)


def test_router_normalizes_methods_and_detects_collisions() -> None:
    permissions = PermissionRegistry()
    permissions.add("plugin:read", "plugin")
    registry = RouterRegistry(permissions)

    def handler() -> None:
        return None

    registry.add("get", "/v1/items", "plugin", handler, permission="plugin:read")
    assert registry.items[0].method == "GET"
    with pytest.raises(PluginValidationError, match="route collision"):
        registry.add("GET", "/v1/items", "plugin", handler, permission="plugin:read")
    with pytest.raises(PluginValidationError, match="route permission"):
        registry.add("GET", "/v1/other", "other", handler, permission="plugin:read")


def test_plugin_context_receives_per_plugin_settings() -> None:
    seen: list[PluginContext] = []

    class Plugin:
        manifest = PluginManifest("com.example.settings", "Settings", "1.0.0", "1.0")

        def register(self, context: PluginContext) -> None:
            seen.append(context)

        def startup(self) -> None:
            pass

        def shutdown(self) -> None:
            pass

    manager = PluginManager()
    manager.compose(
        (PluginRecord(Plugin.manifest, Plugin(), "test"),),
        services={"service": object()},
        settings={"com.example.settings": {"mode": "strict"}},
    )
    assert seen[0].settings == {"mode": "strict"}
    assert "service" in seen[0].services


def test_manager_rejects_recomposition_and_dependency_cycles() -> None:
    class Plugin:
        def __init__(self, manifest: PluginManifest) -> None:
            self.manifest = manifest

        def register(self, _context: PluginContext) -> None:
            pass

        def startup(self) -> None:
            pass

        def shutdown(self) -> None:
            pass

    first_manifest = PluginManifest("com.example.first", "First", "1.0.0", "1.0")
    manager = PluginManager()
    record = PluginRecord(first_manifest, Plugin(first_manifest), "test")
    manager.compose((record,))
    with pytest.raises(PluginValidationError, match="already been composed"):
        manager.compose((record,))

    a_manifest = replace(
        first_manifest,
        id="com.example.a",
        dependencies=(PluginDependency("com.example.b"),),
    )
    b_manifest = replace(
        first_manifest,
        id="com.example.b",
        dependencies=(PluginDependency("com.example.a"),),
    )
    with pytest.raises(PluginValidationError, match="dependency cycle"):
        PluginManager().compose(
            (
                PluginRecord(a_manifest, Plugin(a_manifest), "test"),
                PluginRecord(b_manifest, Plugin(b_manifest), "test"),
            )
        )


def test_openlineage_validator_rejects_each_structural_boundary() -> None:
    event = {
        "eventType": "COMPLETE",
        "eventTime": "2026-01-01T00:00:00Z",
        "run": {"runId": "run"},
        "job": {"namespace": "ns", "name": "job"},
        "producer": "https://github.com/SauronShepherd/ronin",
        "schemaURL": "https://openlineage.io/spec/1-0-5/OpenLineage.json#/definitions/RunEvent",
    }
    for field in ("eventType", "eventTime", "run", "job", "producer", "schemaURL"):
        invalid = dict(event)
        invalid.pop(field)
        with pytest.raises(ValueError, match="OpenLineage (event|run event)"):
            validate_openlineage_event(invalid)
    for invalid in (
        {**event, "eventType": "UNKNOWN"},
        {**event, "eventTime": "2026-01-01T00:00:00"},
        {**event, "run": []},
        {**event, "job": []},
        {**event, "run": {"runId": " "}},
        {**event, "job": {"namespace": "", "name": "job"}},
        {**event, "job": {"namespace": "ns", "name": " "}},
    ):
        with pytest.raises(ValueError, match="OpenLineage (event|run|job)"):
            validate_openlineage_event(invalid)


def test_graph_executor_rejects_ast_type_and_limit_boundaries() -> None:
    executor = LocalGraphQueryExecutor(KnowledgeGraph(()))
    with pytest.raises(TypeError, match="AST"):
        executor.execute("SELECT Customer")  # type: ignore[arg-type]
    for max_limit in (0, 100001):
        with pytest.raises(ValueError, match="between 1 and 100000"):
            executor.execute(parse_rql("SELECT Customer"), max_limit=max_limit)


def test_event_stores_reject_capacity_and_invalid_consumer_without_side_effects() -> None:
    with pytest.raises(ValueError, match="max_events must be positive"):
        InMemoryOutbox(max_events=0)
    with pytest.raises(ValueError, match="max_events must be positive"):
        InMemoryInbox(max_events=0)
    inbox = InMemoryInbox()
    event = new_event(
        event_id="event-1",
        event_type="projects.created.v1",
        producer="example",
        tenant_id="tenant-1",
        correlation_id="correlation-1",
        occurred_at="2026-01-01T00:00:00Z",
        payload={"project_id": "project-1"},
    )
    with pytest.raises(PluginEventError, match="consumer_id"):
        inbox.process_once("\n", event, lambda _: pytest.fail("handler called"))
