from __future__ import annotations

import pytest
from studio_core.plugins import (
    ContributionRegistry,
    PipelineStageContribution,
    PluginManager,
    PluginManifest,
    PluginRecord,
    PluginValidationError,
)


def test_contribution_registries_register_and_sort_non_http_surfaces() -> None:
    registry = ContributionRegistry()

    def handler(**_: object) -> None:
        return None

    registry.add_job("z-job", "example", handler)
    registry.add_job("a-job", "example", handler)
    registry.add_event_subscription("projects.created.v1", "example", handler)
    registry.add_migration("example.001", "example")
    registry.add_ui("example", {"navigation": [{"id": "example"}]})

    assert [item.job_type for item in registry.job_registry.items] == ["a-job", "z-job"]
    assert registry.event_subscription_registry.items[0].event_type == "projects.created.v1"
    assert registry.migration_registry.items[0].migration_id == "example.001"
    assert registry.ui_registry.items[0].manifest["navigation"][0]["id"] == "example"


def test_non_http_registries_reject_collisions_and_freeze() -> None:
    registry = ContributionRegistry()

    def handler(**_: object) -> None:
        return None

    registry.add_job("example", "plugin-a", handler)
    with pytest.raises(PluginValidationError, match="job type collision"):
        registry.add_job("example", "plugin-b", handler)
    registry.add_migration("example.001", "plugin-a")
    with pytest.raises(PluginValidationError, match="migration collision"):
        registry.add_migration("example.001", "plugin-b")
    registry.add_ui("plugin-a", {})
    with pytest.raises(PluginValidationError, match="UI contribution collision"):
        registry.add_ui("plugin-a", {})

    registry.freeze()
    with pytest.raises(PluginValidationError, match="frozen"):
        registry.add_job("later", "plugin-a", handler)


def test_contribution_registries_preserve_same_owner_and_reject_cross_owner_conflicts() -> None:
    registry = ContributionRegistry()

    def handler() -> None:
        return None

    registry.add_capability("example.read", "plugin-a")
    registry.add_capability("example.read", "plugin-a")
    assert registry.capabilities == {"example.read": "plugin-a"}
    with pytest.raises(PluginValidationError, match="capability .* already provided"):
        registry.add_capability("example.read", "plugin-b")

    registry.add_permission("example:read", "plugin-a")
    registry.add_permission("example:read", "plugin-a")
    assert registry.permissions == {"example:read": "plugin-a"}
    with pytest.raises(PluginValidationError, match="permission .* already owned"):
        registry.add_permission("example:read", "plugin-b")

    registry.add_route("get", "/v1/example", "plugin-a", handler, permission="example:read")
    with pytest.raises(PluginValidationError, match="route collision: GET /v1/example"):
        registry.add_route("GET", "/v1/example", "plugin-a", handler, permission="example:read")


def test_contribution_registries_detect_event_and_surface_collisions() -> None:
    registry = ContributionRegistry()

    def handler() -> None:
        return None

    registry.add_event_subscription("example.created", "plugin-a", handler)
    with pytest.raises(PluginValidationError, match="event subscription collision"):
        registry.add_event_subscription("example.created", "plugin-a", handler)

    registry.add_capability("example.read", "plugin-a")
    registry.add_permission("example:read", "plugin-a")
    contribution = {
        "id": "plugin-a.inspect",
        "plugin_id": "plugin-a",
        "namespace": "example",
        "command": "inspect",
        "operation_id": "example.inspect.v1",
        "capability": "example.read",
        "permission": "example:read",
        "path": "/v1/example/inspect",
    }
    from studio_core.plugins import SurfaceContribution

    registry.add_surface(SurfaceContribution(**contribution))
    with pytest.raises(PluginValidationError, match="surface contribution collision"):
        registry.add_surface(SurfaceContribution(**contribution))


def test_all_contribution_registries_are_frozen_together() -> None:
    registry = ContributionRegistry()

    def handler(**_: object) -> None:
        return None

    registry.add_capability("example.read", "plugin-a")
    registry.add_permission("example:read", "plugin-a")
    registry.add_route("get", "/v1/example", "plugin-a", handler, permission="example:read")
    registry.freeze()

    with pytest.raises(PluginValidationError, match="frozen"):
        registry.add_capability("example.write", "plugin-a")
    with pytest.raises(PluginValidationError, match="frozen"):
        registry.add_permission("example:write", "plugin-a")
    with pytest.raises(PluginValidationError, match="frozen"):
        registry.add_route("GET", "/v1/other", "plugin-a", handler, permission="example:read")


def test_plugin_manifest_must_declare_non_http_contributions() -> None:
    class Plugin:
        manifest = PluginManifest(
            id="example",
            name="Example",
            version="1.0.0",
            plugin_api="1.0",
            job_types=("example.job",),
        )

        def register(self, context) -> None:
            context.contributions.add_job("undeclared.job", context.plugin_id, self)

        def startup(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

    plugin = Plugin()
    with pytest.raises(PluginValidationError, match="undeclared job"):
        PluginManager().compose((PluginRecord(plugin.manifest, plugin, "test"),))


def test_pipeline_stage_manifest_must_declare_stage_and_artifact_permissions() -> None:
    stage = PipelineStageContribution(
        plugin_id="com.example.ronin.ml",
        stage_id="com.example.ronin.ml/evaluate",
        version=1,
        plugin_version="1.2.0",
        distribution_digest="a" * 64,
        executor_image="registry.example/ml-plugin@sha256:" + "b" * 64,
        operation_id="evaluate.v1",
        input_ports={"model": ("ml.model", 1, 1)},
        output_type="ml.metrics",
        permissions=("artifact:write",),
        effect="artifact_write",
    )
    registry = ContributionRegistry()
    registry.add_pipeline_stage(stage, plugin_id=stage.plugin_id)
    undeclared = PluginManifest(
        id=stage.plugin_id,
        name="ML stage provider",
        version=stage.plugin_version,
        plugin_api="1.0",
        pipeline_stage_ids=(stage.stage_id,),
    )
    with pytest.raises(PluginValidationError, match="undeclared pipeline stage permission"):
        registry.validate_manifest(undeclared)

    declared = PluginManifest(
        id=stage.plugin_id,
        name="ML stage provider",
        version=stage.plugin_version,
        plugin_api="1.0",
        permissions=("artifact:write",),
        pipeline_stage_ids=(stage.stage_id,),
    )
    registry.validate_manifest(declared)
