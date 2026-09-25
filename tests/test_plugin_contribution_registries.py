from __future__ import annotations

import pytest

from studio_core.plugins import (
    ContributionRegistry,
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
