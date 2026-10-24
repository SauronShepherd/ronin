from __future__ import annotations

import os

import pytest
from studio_observability import MetricPoint, OtlpHttpExporter, TelemetryEvent, TraceSpan
from studio_orchestrator import Instant

_ENDPOINT = os.environ.get("RONIN_OTLP_TEST_ENDPOINT")
pytestmark = pytest.mark.skipif(
    not _ENDPOINT,
    reason="set RONIN_OTLP_TEST_ENDPOINT to qualify a real OTLP collector",
)


def test_real_otlp_collector_accepts_traces_metrics_and_logs() -> None:
    assert _ENDPOINT is not None
    observed_at = Instant("2026-10-24T04:30:00.000000Z")
    exporter = OtlpHttpExporter(_ENDPOINT, request_timeout_seconds=5)
    try:
        assert exporter.export_metrics(
            (
                MetricPoint(
                    "ronin.integration.otlp.rows",
                    3.0,
                    "rows",
                    "counter",
                    observed_at,
                    (("qualification", "real-collector"),),
                ),
            )
        )
        assert exporter.export_events(
            (
                TelemetryEvent(
                    "ronin.integration.otlp.event",
                    "info",
                    observed_at,
                    "real OTLP collector acceptance",
                    (("qualification", "real-collector"),),
                    trace_id="1" * 32,
                    span_id="2" * 16,
                ),
            )
        )
        assert exporter.export_spans(
            (
                TraceSpan(
                    "1" * 32,
                    "2" * 16,
                    "ronin.integration.otlp.span",
                    observed_at,
                    Instant("2026-10-24T04:30:00.001000Z"),
                    (("qualification", "real-collector"),),
                    "ok",
                ),
            )
        )
        assert exporter.flush(timeout_seconds=10)
        stats = exporter.stats
        assert stats.accepted_batches == 3
        assert stats.exported_batches == 3
        assert stats.failed_batches == 0
    finally:
        assert exporter.close(timeout_seconds=10)
