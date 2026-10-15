"""Local-only plugin implementations for logs/traces and metrics."""

from __future__ import annotations

from typing import Any, cast

from studio_core.plugins import PluginContext, PluginManifest, SurfaceContribution

from .buffer import LocalObservabilityBuffer


class LoggingPlugin:
    manifest = PluginManifest(
        id="com.sauronshepherd.ronin.logging",
        name="Ronin Local Logging and Tracing",
        version="0.1.0",
        plugin_api="1.0",
        host_requires=">=1,<2",
        edition="community",
        capabilities=("logging.local", "tracing.local"),
        permissions=("logging:read",),
        surface_ids=("observability.logs.v1", "observability.traces.v1"),
    )

    def __init__(self, buffer: LocalObservabilityBuffer | None = None) -> None:
        self.buffer = buffer or LocalObservabilityBuffer()
        self.started = False

    def register(self, context: PluginContext) -> None:
        injected = context.services.get("observability_buffer")
        if injected is not None:
            self.buffer = cast(LocalObservabilityBuffer, injected)
        context.contributions.add_route(
            "GET", "/v1/platform/logs", context.plugin_id, self.logs, permission="logging:read"
        )
        context.contributions.add_route(
            "GET", "/v1/platform/traces", context.plugin_id, self.traces, permission="logging:read"
        )
        for contribution in (
            SurfaceContribution(
                id="observability.logs.v1",
                plugin_id=context.plugin_id,
                namespace="observability",
                command="logs",
                operation_id="observability.logs.v1",
                capability="logging.local",
                permission="logging:read",
                path="/v1/platform/logs",
                method="GET",
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="observability.traces.v1",
                plugin_id=context.plugin_id,
                namespace="observability",
                command="traces",
                operation_id="observability.traces.v1",
                capability="tracing.local",
                permission="logging:read",
                path="/v1/platform/traces",
                method="GET",
                output_schema={"type": "object"},
            ),
        ):
            context.contributions.add_surface(contribution)

    def startup(self) -> None:
        self.started = True

    def shutdown(self) -> None:
        self.started = False

    def logs(self, *, query: str | None = None, **_kwargs: Any) -> dict[str, object]:
        return {"items": list(self.buffer.logs(limit=_limit_from_query(query)))}

    def traces(self, *, query: str | None = None, **_kwargs: Any) -> dict[str, object]:
        return {"items": list(self.buffer.traces(limit=_limit_from_query(query)))}


class MonitoringPlugin:
    manifest = PluginManifest(
        id="com.sauronshepherd.ronin.monitoring",
        name="Ronin Local Monitoring",
        version="0.1.0",
        plugin_api="1.0",
        host_requires=">=1,<2",
        edition="community",
        capabilities=("monitoring.local",),
        permissions=("monitoring:read",),
        surface_ids=("observability.metrics.v1",),
    )

    def __init__(self, buffer: LocalObservabilityBuffer | None = None) -> None:
        self.buffer = buffer or LocalObservabilityBuffer()
        self.started = False

    def register(self, context: PluginContext) -> None:
        injected = context.services.get("observability_buffer")
        if injected is not None:
            self.buffer = cast(LocalObservabilityBuffer, injected)
        context.contributions.add_route(
            "GET",
            "/v1/platform/metrics",
            context.plugin_id,
            self.metrics,
            permission="monitoring:read",
        )
        context.contributions.add_surface(
            SurfaceContribution(
                id="observability.metrics.v1",
                plugin_id=context.plugin_id,
                namespace="observability",
                command="metrics",
                operation_id="observability.metrics.v1",
                capability="monitoring.local",
                permission="monitoring:read",
                path="/v1/platform/metrics",
                method="GET",
                output_schema={"type": "object"},
            )
        )

    def startup(self) -> None:
        self.started = True

    def shutdown(self) -> None:
        self.started = False

    def metrics(self, *, query: str | None = None, **_kwargs: Any) -> dict[str, object]:
        return {"items": list(self.buffer.metrics(limit=_limit_from_query(query)))}


def _limit_from_query(query: str | None) -> int:
    if not query:
        return 100
    for part in query.split("&"):
        key, _, value = part.partition("=")
        if key == "limit":
            return int(value)
    return 100


def logging_factory() -> LoggingPlugin:
    return LoggingPlugin()


def monitoring_factory() -> MonitoringPlugin:
    return MonitoringPlugin()


__all__ = ("LoggingPlugin", "MonitoringPlugin", "logging_factory", "monitoring_factory")
