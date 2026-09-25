from __future__ import annotations

from studio_core.plugin_events import PluginEventSchema, PluginEventSchemaRegistry
from studio_core.workspaces import WorkspaceId
from studio_plugin_workspaces import WorkspacesPlugin


class _Dispatcher:
    def __init__(self) -> None:
        self.events = []

    def publish(self, event) -> None:
        self.events.append(event)


def test_workspaces_plugin_emits_versioned_project_event_when_dispatcher_is_injected() -> None:
    dispatcher = _Dispatcher()
    plugin = WorkspacesPlugin()
    plugin._event_dispatcher = dispatcher

    plugin._publish(
        "projects.project-created.v1",
        WorkspaceId("workspace-1"),
        {"project_id": "project-1"},
        "create-1",
    )

    assert plugin.manifest.event_types[0] == "projects.project-created.v1"
    assert dispatcher.events[0].event_type == "projects.project-created.v1"


def test_workspace_event_schemas_are_explicitly_versioned() -> None:
    registry = PluginEventSchemaRegistry()
    for event_type, field in (
        ("projects.project-created.v1", "project_id"),
        ("projects.project-updated.v1", "project_id"),
        ("projects.project-deleted.v1", "project_id"),
    ):
        registry.register(PluginEventSchema(event_type, 1, (field,)))

    assert [item.event_type for item in registry.items] == [
        "projects.project-created.v1",
        "projects.project-deleted.v1",
        "projects.project-updated.v1",
    ]
