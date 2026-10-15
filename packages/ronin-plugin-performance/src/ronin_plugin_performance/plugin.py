from __future__ import annotations

from studio_core.plugins import PluginContext, PluginManifest, SurfaceContribution

from .resources import load_config_schema, load_ui_manifest
from .service import analyze_http, analyze_performance

PLUGIN_ID = "com.sauronshepherd.ronin.performance"


class PerformancePlugin:
    manifest = PluginManifest(
        id=PLUGIN_ID,
        name="Performance Studio",
        version="0.1.0",
        plugin_api="1.0",
        isolation="worker",
        capabilities=(
            "performance.analysis",
            "performance.visualizations",
            "performance.recommendations",
        ),
        permissions=("performance:read", "performance:analyze"),
        job_types=("performance.analyze",),
        ui_entry="ronin_plugin_performance/ui_manifest.json",
        config_schema="ronin.performance/config-v1",
        surface_ids=("performance.analyze.v1",),
    )

    def register(self, context: PluginContext) -> None:
        ui_manifest = load_ui_manifest()
        load_config_schema()
        context.contributions.add_capability("performance.analysis", PLUGIN_ID)
        context.contributions.add_capability("performance.visualizations", PLUGIN_ID)
        context.contributions.add_capability("performance.recommendations", PLUGIN_ID)
        for permission in self.manifest.permissions:
            context.contributions.add_permission(permission, PLUGIN_ID)
        context.contributions.add_job("performance.analyze", PLUGIN_ID, analyze_performance)
        context.contributions.add_route(
            "POST",
            "/api/v1/performance/analyze",
            PLUGIN_ID,
            analyze_http,
            permission="performance:analyze",
        )
        context.contributions.add_surface(
            SurfaceContribution(
                id="performance.analyze.v1",
                plugin_id=PLUGIN_ID,
                namespace="performance",
                command="analyze",
                operation_id="performance.analyze.v1",
                capability="performance.analysis",
                permission="performance:analyze",
                path="/api/v1/performance/analyze",
                method="POST",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )
        )
        context.contributions.add_ui(
            PLUGIN_ID,
            {
                "ui_api": ui_manifest["ui_api"],
                "product": ui_manifest["product"],
                "entry": self.manifest.ui_entry,
                "navigation": [
                    {
                        "id": "performance",
                        "label": "Performance Studio",
                        "permission": "performance:read",
                    }
                ],
                "charts": ui_manifest["charts"],
            },
        )

    def startup(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


def factory() -> PerformancePlugin:
    return PerformancePlugin()
