"""Bounded, best-effort OTLP/HTTP exporter for Ronin telemetry contracts."""

from __future__ import annotations

import json
import math
import os
import queue
import re
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

from studio_orchestrator import Instant

from .contracts import MetricPoint, TelemetryEvent

_SENSITIVE_KEY_PARTS = (
    "authorization",
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "api_key",
    "apikey",
    "private_key",
)
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(authorization|password|passwd|secret|token|credential|api[_-]?key|private[_-]?key)\b"
    r"\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)


def _safe_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{name} must be non-empty text")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ValueError(f"{name} must be valid UTF-8 text") from exc
    if size > 65_536:
        raise ValueError(f"{name} exceeds the 65536-byte limit")
    return value


def _redact_text(value: str) -> str:
    value = _BEARER_PATTERN.sub("Bearer [REDACTED]", value)
    return _SECRET_ASSIGNMENT_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)


def _otlp_attributes(values: Iterable[tuple[str, str]]) -> list[dict[str, object]]:
    selected = list(values)
    if len(selected) > 64:
        raise ValueError("OTLP attributes exceed their configured count or size bounds")
    for entry in selected:
        if not isinstance(entry, tuple) or len(entry) != 2:
            raise ValueError("OTLP attributes must be key/value pairs")
        _safe_text(entry[0], "OTLP attribute key")
        _safe_text(entry[1], "OTLP attribute value")
    selected.sort()
    if len({key for key, _ in selected}) != len(selected):
        raise ValueError("OTLP attribute keys must be unique")
    attributes: list[dict[str, object]] = []
    total_bytes = 0
    for key, value in selected:
        _safe_text(key, "OTLP attribute key")
        _safe_text(value, "OTLP attribute value")
        total_bytes += len(key.encode("utf-8")) + len(value.encode("utf-8"))
        if total_bytes > 65_536:
            raise ValueError("OTLP attributes exceed their configured count or size bounds")
        is_sensitive = any(
            part in key.casefold().replace("-", "_") for part in _SENSITIVE_KEY_PARTS
        )
        attributes.append(
            {
                "key": key,
                "value": {"stringValue": "[REDACTED]" if is_sensitive else _redact_text(value)},
            }
        )
    return attributes


def _unix_nanos(value: Instant) -> str:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("OTLP timestamps must include a timezone")
    utc = parsed.astimezone(UTC)
    seconds = int(utc.timestamp())
    return str(seconds * 1_000_000_000 + utc.microsecond * 1_000)


@dataclass(frozen=True, slots=True)
class TraceSpan:
    """Small provider-neutral span contract mapped to OTLP trace records."""

    trace_id: str
    span_id: str
    name: str
    start_time: Instant
    end_time: Instant
    attributes: tuple[tuple[str, str], ...] = ()
    status: Literal["unset", "ok", "error"] = "unset"

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-fA-F]{32}", self.trace_id):
            raise ValueError("trace_id must be 32 hexadecimal characters")
        if not re.fullmatch(r"[0-9a-fA-F]{16}", self.span_id):
            raise ValueError("span_id must be 16 hexadecimal characters")
        _safe_text(self.name, "span name")
        start = Instant(self.start_time)
        end = Instant(self.end_time)
        if end < start:
            raise ValueError("span end_time must not precede start_time")
        if self.status not in {"unset", "ok", "error"}:
            raise ValueError("unsupported span status")
        _otlp_attributes(self.attributes)
        object.__setattr__(self, "start_time", start)
        object.__setattr__(self, "end_time", end)


@dataclass(frozen=True, slots=True)
class OtlpExporterStats:
    accepted_batches: int
    exported_batches: int
    failed_batches: int
    backpressure_batches: int
    pending_batches: int
    closed: bool


@dataclass(frozen=True, slots=True)
class _QueuedPayload:
    signal: Literal["traces", "metrics", "logs"]
    body: bytes


class OtlpHttpExporter:
    """Export normalized telemetry in a bounded background queue.

    Queue saturation returns ``False`` to the caller. Network and collector errors
    are counted in ``stats`` and never escape the background worker into job code.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        resource_attributes: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        sensitive_values: Iterable[str] = (),
        max_queue_batches: int = 64,
        max_records_per_batch: int = 256,
        max_payload_bytes: int = 262_144,
        request_timeout_seconds: float = 2.0,
        scope_name: str = "ronin",
        scope_version: str = "1",
    ) -> None:
        if (
            not isinstance(endpoint, str)
            or endpoint != endpoint.strip()
            or "\r" in endpoint
            or "\n" in endpoint
        ):
            raise ValueError("OTLP endpoint must be trimmed and single-line")
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("OTLP endpoint must be an HTTP(S) base URL without credentials/query")
        try:
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("OTLP endpoint port is invalid") from exc
        if max_queue_batches < 1 or max_queue_batches > 4096:
            raise ValueError("max_queue_batches must be between 1 and 4096")
        if max_records_per_batch < 1 or max_records_per_batch > 10_000:
            raise ValueError("max_records_per_batch must be between 1 and 10000")
        if max_payload_bytes < 1024 or max_payload_bytes > 4_194_304:
            raise ValueError("max_payload_bytes must be between 1024 and 4194304")
        if not math.isfinite(request_timeout_seconds) or not 0.05 <= request_timeout_seconds <= 60:
            raise ValueError("request_timeout_seconds must be finite and between 0.05 and 60")
        self._endpoint = endpoint.rstrip("/")
        self._headers = self._validate_headers(headers or {})
        configured_secrets = tuple(sensitive_values)
        if any(not isinstance(value, str) for value in configured_secrets):
            raise ValueError("sensitive_values must contain text values")
        self._sensitive_values = tuple(
            dict.fromkeys(
                value
                for value in (*(value for _, value in self._headers), *configured_secrets)
                if value
            )
        )
        for value in self._sensitive_values:
            _safe_text(value, "sensitive value")
        if (
            len(self._sensitive_values) > 64
            or sum(len(value.encode("utf-8")) for value in self._sensitive_values) > 65_536
        ):
            raise ValueError("sensitive_values exceed their configured count or size bounds")
        attributes = dict(resource_attributes or {})
        attributes.setdefault("service.name", "ronin")
        self._resource_attributes = tuple(sorted(attributes.items()))
        _otlp_attributes(self._resource_attributes)
        self._max_records_per_batch = max_records_per_batch
        self._max_payload_bytes = max_payload_bytes
        self._request_timeout_seconds = request_timeout_seconds
        self._scope_name = _safe_text(scope_name, "scope_name")
        self._scope_version = _safe_text(scope_version, "scope_version")
        self._queue: queue.Queue[_QueuedPayload | None] = queue.Queue(maxsize=max_queue_batches)
        self._condition = threading.Condition()
        self._accepted_batches = 0
        self._exported_batches = 0
        self._failed_batches = 0
        self._backpressure_batches = 0
        self._pending_batches = 0
        self._closed = False
        self._stop_sent = False
        self._worker = threading.Thread(target=self._run, name="ronin-otlp-exporter", daemon=True)
        self._worker.start()

    @classmethod
    def from_environment(cls) -> OtlpHttpExporter:
        """Create an exporter from standard OTLP endpoint/header environment values."""
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
        if not endpoint:
            raise ValueError("OTEL_EXPORTER_OTLP_ENDPOINT must be set")
        headers: dict[str, str] = {}
        for entry in os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "").split(","):
            if not entry:
                continue
            name, separator, value = entry.partition("=")
            if not separator or not name.strip():
                raise ValueError("OTEL_EXPORTER_OTLP_HEADERS must contain key=value pairs")
            headers[unquote(name.strip())] = unquote(value.strip())
        resource_attributes = {"service.name": os.environ.get("OTEL_SERVICE_NAME", "ronin")}
        for entry in os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "").split(","):
            if not entry:
                continue
            name, separator, value = entry.partition("=")
            if not separator or not name.strip():
                raise ValueError("OTEL_RESOURCE_ATTRIBUTES must contain key=value pairs")
            resource_attributes[unquote(name.strip())] = unquote(value.strip())
        return cls(
            endpoint,
            resource_attributes=resource_attributes,
            headers=headers,
            sensitive_values=headers.values(),
        )

    @staticmethod
    def _validate_headers(headers: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
        if len(headers) > 64:
            raise ValueError("OTLP header count exceeds its configured limit")
        normalized: list[tuple[str, str]] = []
        normalized_names: set[str] = set()
        for name, value in headers.items():
            if not isinstance(name, str) or not re.fullmatch(
                r"[!#$%&'*+.^_`|~0-9A-Za-z-]{1,256}", name
            ):
                raise ValueError("OTLP header name is invalid")
            canonical_name = name.casefold()
            if canonical_name in normalized_names or canonical_name == "content-type":
                raise ValueError("OTLP headers must be unique and cannot override Content-Type")
            normalized_names.add(canonical_name)
            if (
                not isinstance(value, str)
                or "\r" in value
                or "\n" in value
                or len(value.encode("utf-8")) > 8192
            ):
                raise ValueError("OTLP header values must be single-line text")
            normalized.append((name, value))
        if (
            sum(
                len(name.encode("utf-8")) + len(value.encode("utf-8")) for name, value in normalized
            )
            > 65_536
        ):
            raise ValueError("OTLP headers exceed their configured size bound")
        return tuple(normalized)

    def _scope(self) -> dict[str, str]:
        return {"name": self._scope_name, "version": self._scope_version}

    def _resource(self) -> dict[str, object]:
        return {"attributes": self._attributes(self._resource_attributes)}

    def _redact(self, value: str) -> str:
        redacted = _redact_text(value)
        for secret in self._sensitive_values:
            redacted = redacted.replace(secret, "[REDACTED]")
        return redacted

    def _attributes(self, values: Iterable[tuple[str, str]]) -> list[dict[str, object]]:
        selected: list[tuple[str, str]] = []
        for key, value in values:
            if any(part in key.casefold().replace("-", "_") for part in _SENSITIVE_KEY_PARTS):
                selected.append((key, "[REDACTED]"))
            else:
                selected.append((key, self._redact(value)))
        return _otlp_attributes(selected)

    def _enqueue(self, signal: Literal["traces", "metrics", "logs"], payload: object) -> bool:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if len(body) > self._max_payload_bytes:
            raise ValueError("OTLP payload exceeds max_payload_bytes")
        with self._condition:
            if self._closed:
                return False
            try:
                self._queue.put_nowait(_QueuedPayload(signal, body))
            except queue.Full:
                self._backpressure_batches += 1
                return False
            self._accepted_batches += 1
            self._pending_batches += 1
            return True

    def export_metrics(self, points: Iterable[MetricPoint]) -> bool:
        records = tuple(points)
        if not records:
            return True
        if len(records) > self._max_records_per_batch:
            raise ValueError("OTLP metric batch exceeds max_records_per_batch")
        metrics: list[dict[str, object]] = []
        for point in records:
            timestamp = _unix_nanos(point.observed_at)
            data_point = {
                "timeUnixNano": timestamp,
                "asDouble": point.value,
                "attributes": self._attributes(point.attributes),
            }
            if point.kind == "counter":
                data_point["startTimeUnixNano"] = str(max(0, int(timestamp) - 1))
                metric: dict[str, object] = {
                    "name": point.name,
                    "unit": point.unit,
                    "sum": {
                        "aggregationTemporality": 1,
                        "isMonotonic": True,
                        "dataPoints": [data_point],
                    },
                }
            else:
                metric = {
                    "name": point.name,
                    "unit": point.unit,
                    "gauge": {"dataPoints": [data_point]},
                }
            metrics.append(metric)
        return self._enqueue(
            "metrics",
            {
                "resourceMetrics": [
                    {
                        "resource": self._resource(),
                        "scopeMetrics": [{"scope": self._scope(), "metrics": metrics}],
                    }
                ]
            },
        )

    def export_events(self, events: Iterable[TelemetryEvent]) -> bool:
        records = tuple(events)
        if not records:
            return True
        if len(records) > self._max_records_per_batch:
            raise ValueError("OTLP log batch exceeds max_records_per_batch")
        severity = {
            "debug": (5, "DEBUG"),
            "info": (9, "INFO"),
            "warning": (13, "WARN"),
            "error": (17, "ERROR"),
            "critical": (21, "FATAL"),
        }
        log_records: list[dict[str, object]] = []
        for event in records:
            severity_number, severity_text = severity[event.severity]
            attributes = [("ronin.event.name", event.name), *event.attributes]
            record: dict[str, object] = {
                "timeUnixNano": _unix_nanos(event.occurred_at),
                "observedTimeUnixNano": _unix_nanos(event.occurred_at),
                "severityNumber": severity_number,
                "severityText": severity_text,
                "body": {"stringValue": self._redact(event.message)},
                "attributes": self._attributes(attributes),
            }
            if event.trace_id is not None:
                if not re.fullmatch(r"[0-9a-fA-F]{32}", event.trace_id):
                    raise ValueError("telemetry event trace_id must be 32 hexadecimal characters")
                record["traceId"] = event.trace_id.lower()
            if event.span_id is not None:
                if not re.fullmatch(r"[0-9a-fA-F]{16}", event.span_id):
                    raise ValueError("telemetry event span_id must be 16 hexadecimal characters")
                record["spanId"] = event.span_id.lower()
            log_records.append(record)
        return self._enqueue(
            "logs",
            {
                "resourceLogs": [
                    {
                        "resource": self._resource(),
                        "scopeLogs": [{"scope": self._scope(), "logRecords": log_records}],
                    }
                ]
            },
        )

    def export_spans(self, spans: Iterable[TraceSpan]) -> bool:
        records = tuple(spans)
        if not records:
            return True
        if len(records) > self._max_records_per_batch:
            raise ValueError("OTLP trace batch exceeds max_records_per_batch")
        otlp_spans = []
        for span in records:
            status_code = {"unset": 0, "ok": 1, "error": 2}[span.status]
            otlp_spans.append(
                {
                    "traceId": span.trace_id.lower(),
                    "spanId": span.span_id.lower(),
                    "name": self._redact(span.name),
                    "kind": 1,
                    "startTimeUnixNano": _unix_nanos(span.start_time),
                    "endTimeUnixNano": _unix_nanos(span.end_time),
                    "attributes": self._attributes(span.attributes),
                    "status": {"code": status_code},
                }
            )
        return self._enqueue(
            "traces",
            {
                "resourceSpans": [
                    {
                        "resource": self._resource(),
                        "scopeSpans": [{"scope": self._scope(), "spans": otlp_spans}],
                    }
                ]
            },
        )

    def record_metric(self, point: MetricPoint) -> bool:
        """Callback-compatible single-point metrics export for instrumentation."""
        return self._callback_export(lambda: self.export_metrics((point,)))

    def record_event(self, event: TelemetryEvent) -> bool:
        """Callback-compatible event export for instrumentation."""
        return self._callback_export(lambda: self.export_events((event,)))

    def _callback_export(self, export: Callable[[], bool]) -> bool:
        try:
            return export()
        except Exception:
            with self._condition:
                self._failed_batches += 1
            return False

    def _send(self, item: _QueuedPayload) -> None:
        request = Request(  # noqa: S310 - endpoint is validated as HTTP(S) in __init__
            f"{self._endpoint}/v1/{item.signal}",
            data=item.body,
            headers={"Content-Type": "application/json", **dict(self._headers)},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._request_timeout_seconds) as response:  # noqa: S310
                if not 200 <= response.status < 300:
                    raise OtlpExportError(f"collector returned HTTP {response.status}")
                response.read(65_537)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise OtlpExportError("OTLP collector request failed") from exc

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                return
            try:
                self._send(item)
            except Exception:
                with self._condition:
                    self._failed_batches += 1
            else:
                with self._condition:
                    self._exported_batches += 1
            finally:
                self._queue.task_done()
                with self._condition:
                    self._pending_batches -= 1
                    self._condition.notify_all()

    def flush(self, timeout_seconds: float = 5.0) -> bool:
        if not math.isfinite(timeout_seconds) or timeout_seconds < 0:
            raise ValueError("flush timeout must be finite and non-negative")
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            while self._pending_batches:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    def close(self, timeout_seconds: float = 5.0) -> bool:
        if not math.isfinite(timeout_seconds) or timeout_seconds < 0:
            raise ValueError("close timeout must be finite and non-negative")
        with self._condition:
            self._closed = True
        if not self.flush(timeout_seconds):
            return False
        with self._condition:
            if not self._stop_sent:
                self._queue.put_nowait(None)
                self._stop_sent = True
        self._worker.join(timeout_seconds)
        return not self._worker.is_alive()

    @property
    def stats(self) -> OtlpExporterStats:
        with self._condition:
            return OtlpExporterStats(
                self._accepted_batches,
                self._exported_batches,
                self._failed_batches,
                self._backpressure_batches,
                self._pending_batches,
                self._closed,
            )

    def __enter__(self) -> OtlpHttpExporter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class OtlpExportError(RuntimeError):
    """Raised internally for an unsuccessful collector response."""


__all__ = ("OtlpExportError", "OtlpExporterStats", "OtlpHttpExporter", "TraceSpan")
