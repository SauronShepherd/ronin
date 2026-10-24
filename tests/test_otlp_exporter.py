from __future__ import annotations

import json
from collections.abc import Iterable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from typing import Literal, cast

import pytest
from studio_observability import (
    MetricPoint,
    OtlpHttpExporter,
    TelemetryEvent,
    TraceSpan,
    instrument_execution,
)
from studio_orchestrator import Instant


class _Collector(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        *,
        block: bool = False,
        status: int = 200,
    ) -> None:
        self.received: list[tuple[str, bytes, dict[str, str]]] = []
        self.request_started = Event()
        self.release_request = Event()
        self.block = block
        self.response_status = status
        super().__init__(("127.0.0.1", 0), _CollectorHandler)


class _CollectorHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        server = cast(_Collector, self.server)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        server.received.append((self.path, body, dict(self.headers.items())))
        server.request_started.set()
        if server.block:
            server.release_request.wait(timeout=5)
        response = b"{}"
        self.send_response(server.response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, _format: str, *args: object) -> None:
        del args


def _start_collector(*, block: bool = False, status: int = 200) -> tuple[_Collector, Thread]:
    collector = _Collector(block=block, status=status)
    thread = Thread(target=collector.serve_forever, daemon=True)
    thread.start()
    return collector, thread


def _metric(name: str = "ronin.rows", kind: Literal["gauge", "counter"] = "gauge") -> MetricPoint:
    return MetricPoint(
        name,
        12.5,
        "rows",
        kind,
        Instant("2026-10-24T00:00:01.000000Z"),
        (("workspace", "default"),),
    )


def test_otlp_exporter_sends_traces_metrics_and_redacted_logs() -> None:
    collector, collector_thread = _start_collector()
    secret = "".join(("collector", "-secret-value"))
    exporter = OtlpHttpExporter(
        f"http://127.0.0.1:{collector.server_port}/collector",
        resource_attributes={
            "service.name": "ronin-test",
            "deployment.environment": "test",
            "password": "resource-secret",
        },
        headers={"X-API-Key": secret},
    )
    try:
        assert exporter.export_metrics((_metric(), _metric("ronin.completed", "counter")))
        assert exporter.export_events(
            (
                TelemetryEvent(
                    "execution.failed",
                    "error",
                    Instant("2026-10-24T00:00:02.000000Z"),
                    f"failed with password=inline-secret and {secret}",
                    (("password", "secret-value"), ("reason", "token=inline-token")),
                    trace_id="a" * 32,
                    span_id="b" * 16,
                ),
            )
        )
        assert exporter.export_spans(
            (
                TraceSpan(
                    "a" * 32,
                    "b" * 16,
                    "quality.evaluate",
                    Instant("2026-10-24T00:00:01.000000Z"),
                    Instant("2026-10-24T00:00:02.000000Z"),
                    (("dataset", "customers"),),
                    "error",
                ),
            )
        )
        assert exporter.flush(timeout_seconds=5)

        received = {
            path.rsplit("/", 1)[-1]: json.loads(body) for path, body, _ in collector.received
        }
        assert set(received) == {"metrics", "logs", "traces"}
        metric = received["metrics"]["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
        assert metric[0]["gauge"]["dataPoints"][0]["asDouble"] == 12.5
        assert metric[1]["sum"]["aggregationTemporality"] == 1
        assert metric[1]["sum"]["isMonotonic"] is True
        event = received["logs"]["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]
        assert event["severityText"] == "ERROR"
        assert event["observedTimeUnixNano"] == event["timeUnixNano"]
        assert event["traceId"] == "a" * 32
        assert event["spanId"] == "b" * 16
        span = received["traces"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        assert span["status"]["code"] == 2
        serialized = json.dumps(received)
        for secret_value in (
            secret,
            "inline-secret",
            "secret-value",
            "inline-token",
            "resource-secret",
        ):
            assert secret_value not in serialized
        assert exporter.stats.accepted_batches == 3
        assert exporter.stats.exported_batches == 3
        assert exporter.stats.failed_batches == 0
    finally:
        assert exporter.close(timeout_seconds=5)
        collector.shutdown()
        collector.server_close()
        collector_thread.join(timeout=5)


def test_otlp_queue_backpressure_is_bounded_and_reported() -> None:
    collector, collector_thread = _start_collector(block=True)
    exporter = OtlpHttpExporter(
        f"http://127.0.0.1:{collector.server_port}",
        max_queue_batches=1,
        request_timeout_seconds=5,
    )
    try:
        assert exporter.export_metrics((_metric("first"),))
        assert collector.request_started.wait(timeout=2)
        assert exporter.export_metrics((_metric("queued"),))
        assert not exporter.export_metrics((_metric("rejected"),))
        assert exporter.stats.backpressure_batches == 1
        collector.release_request.set()
        assert exporter.flush(timeout_seconds=5)
        assert exporter.stats.exported_batches == 2
        assert exporter.stats.pending_batches == 0
    finally:
        collector.release_request.set()
        assert exporter.close(timeout_seconds=5)
        collector.shutdown()
        collector.server_close()
        collector_thread.join(timeout=5)


def test_collector_failure_does_not_change_execution_result() -> None:
    collector, collector_thread = _start_collector(status=503)
    exporter = OtlpHttpExporter(f"http://127.0.0.1:{collector.server_port}")
    try:
        result = instrument_execution(
            "preview",
            lambda: "job-result",
            record_metric=exporter.record_metric,
            record_event=exporter.record_event,
            observed_at=Instant("2026-10-24T00:00:03.000000Z"),
        )
        assert result == "job-result"
        assert exporter.flush(timeout_seconds=5)
        assert exporter.stats.failed_batches == 1
        assert exporter.stats.exported_batches == 0
    finally:
        assert exporter.close(timeout_seconds=5)
        collector.shutdown()
        collector.server_close()
        collector_thread.join(timeout=5)


def test_invalid_telemetry_does_not_mask_execution_failure() -> None:
    collector, collector_thread = _start_collector()
    exporter = OtlpHttpExporter(
        f"http://127.0.0.1:{collector.server_port}",
        max_payload_bytes=1024,
    )
    original_error = RuntimeError("x" * 2048)

    def fail_action() -> str:
        raise original_error

    try:
        with pytest.raises(RuntimeError) as captured:
            instrument_execution(
                "preview",
                fail_action,
                record_metric=exporter.record_metric,
                record_event=exporter.record_event,
                observed_at=Instant("2026-10-24T00:00:03.000000Z"),
            )
        assert captured.value is original_error
        assert exporter.stats.failed_batches == 1
        assert exporter.stats.pending_batches == 0
    finally:
        assert exporter.close(timeout_seconds=5)
        collector.shutdown()
        collector.server_close()
        collector_thread.join(timeout=5)


def test_otlp_exporter_rejects_unbounded_or_unsafe_configuration() -> None:
    with pytest.raises(ValueError, match=r"HTTP\(S\)"):
        OtlpHttpExporter("file:///tmp/collector")
    with pytest.raises(ValueError, match="max_queue_batches"):
        OtlpHttpExporter("http://127.0.0.1:4318", max_queue_batches=0)
    with pytest.raises(ValueError, match="single-line"):
        OtlpHttpExporter("http://127.0.0.1:4318", headers={"X-Test": "line\nbreak"})
    with pytest.raises(ValueError, match="Content-Type"):
        OtlpHttpExporter("http://127.0.0.1:4318", headers={"content-type": "text/plain"})
    with pytest.raises(ValueError, match="sensitive_values"):
        OtlpHttpExporter(
            "http://127.0.0.1:4318",
            sensitive_values=cast(Iterable[str], (object(),)),
        )
