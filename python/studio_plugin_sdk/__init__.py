"""Public, provider-neutral SDK surface for Ronin plugin authors."""

from studio_core.plugin_events import (
    PluginEvent,
    PluginEventSchema,
    PluginEventSchemaRegistry,
    new_event,
)
from studio_core.plugins import (
    CliContributionRegistry,
    ClientOperationRegistry,
    PluginContext,
    PluginDependency,
    PluginManifest,
    PluginRecord,
    PluginState,
    RoninPlugin,
    SurfaceContribution,
    SurfaceOption,
)

__all__ = (
    "PluginContext",
    "PluginDependency",
    "PluginEvent",
    "PluginEventSchema",
    "PluginEventSchemaRegistry",
    "PluginManifest",
    "PluginRecord",
    "PluginState",
    "RoninPlugin",
    "CliContributionRegistry",
    "ClientOperationRegistry",
    "SurfaceContribution",
    "SurfaceOption",
    "new_event",
)
