from __future__ import annotations

from studio_core.plugins import PluginManager, PluginRecord
from studio_plugin_observability import (
    LocalObservability,
    LocalObservabilityBuffer,
    LoggingPlugin,
    MonitoringPlugin,
)


def test_local_observability_buffer_redacts_secrets_and_bounds_records() -> None:
    buffer = LocalObservabilityBuffer(max_records=1)
    buffer.log("info", "started", "example", {"token": "secret", "safe": "value"})
    buffer.log("warning", "continued", "example")
    buffer.trace("trace-1", "span-1", "example.operation", "example", 2.5)
    buffer.metric("ronin.example", 1, "example")

    assert buffer.logs()[0]["message"] == "continued"
    assert buffer.logs()[0]["attributes"] == {}
    assert buffer.traces()[0]["duration_ms"] == 2.5
    assert buffer.metrics()[0]["value"] == 1.0


def test_local_logging_and_monitoring_plugins_compose_with_shared_buffer() -> None:
    buffer = LocalObservabilityBuffer()
    logging_plugin = LoggingPlugin(buffer)
    monitoring_plugin = MonitoringPlugin(buffer)
    manager = PluginManager()

    plan = manager.compose(
        (
            PluginRecord(logging_plugin.manifest, logging_plugin, "test"),
            PluginRecord(monitoring_plugin.manifest, monitoring_plugin, "test"),
        ),
        services={"observability_buffer": buffer},
    )

    assert sorted(route.path for route in plan.contributions.routes) == [
        "/v1/platform/logs",
        "/v1/platform/metrics",
        "/v1/platform/traces",
    ]
    assert plan.contributions.capabilities["logging.local"] == logging_plugin.manifest.id
    assert plan.contributions.capabilities["monitoring.local"] == monitoring_plugin.manifest.id


def test_namespaced_facade_attributes_extensions_and_closes_spans() -> None:
    buffer = LocalObservabilityBuffer()
    telemetry = LocalObservability("com.example.extension", buffer)

    telemetry.log("info", "extension started", {"authorization": "bearer secret"})
    telemetry.metric("extension.items", 3)
    with telemetry.span("extension.process", {"token": "secret"}) as identifiers:
        assert len(identifiers[0]) == 32
        assert len(identifiers[1]) == 16

    assert buffer.logs()[0]["plugin_id"] == "com.example.extension"
    assert buffer.logs()[0]["attributes"]["authorization"] == "[REDACTED]"
    assert buffer.metrics()[0]["plugin_id"] == "com.example.extension"
    span = buffer.traces()[0]
    assert span["plugin_id"] == "com.example.extension"
    redacted_token = span["attributes"]["token"]
    assert redacted_token == "[REDACTED]"  # noqa: S105
    assert span["duration_ms"] >= 0
