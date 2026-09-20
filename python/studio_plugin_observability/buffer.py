"""Bounded local observability buffer with payload redaction."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from threading import Lock
from time import monotonic
from typing import Any
from uuid import uuid4

_SENSITIVE = frozenset({"authorization", "password", "secret", "token", "api_key"})


def _redact(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if str(key).lower() in _SENSITIVE else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class LocalLogEntry:
    occurred_at: str
    level: str
    message: str
    plugin_id: str
    attributes: dict[str, object]


@dataclass(frozen=True, slots=True)
class LocalTraceSpan:
    started_at: str
    trace_id: str
    span_id: str
    operation: str
    plugin_id: str
    duration_ms: float
    attributes: dict[str, object]


@dataclass(frozen=True, slots=True)
class LocalMetric:
    observed_at: str
    name: str
    value: float
    plugin_id: str
    attributes: dict[str, object]


class LocalObservabilityBuffer:
    def __init__(self, *, max_records: int = 10_000) -> None:
        if max_records < 1:
            raise ValueError("max_records must be positive")
        self._max_records = max_records
        self._logs: list[LocalLogEntry] = []
        self._traces: list[LocalTraceSpan] = []
        self._metrics: list[LocalMetric] = []
        self._lock = Lock()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")

    def log(
        self,
        level: str,
        message: str,
        plugin_id: str,
        attributes: dict[str, object] | None = None,
    ) -> None:
        if level not in {"debug", "info", "warning", "error"} or not message.strip():
            raise ValueError("invalid local log entry")
        entry = LocalLogEntry(
            self._now(), level, message.strip(), plugin_id, _redact(attributes or {})
        )
        with self._lock:
            self._logs.append(entry)
            del self._logs[: max(0, len(self._logs) - self._max_records)]

    def trace(
        self,
        trace_id: str,
        span_id: str,
        operation: str,
        plugin_id: str,
        duration_ms: float,
        attributes: dict[str, object] | None = None,
    ) -> None:
        if not trace_id or not span_id or not operation.strip() or duration_ms < 0:
            raise ValueError("invalid local trace span")
        entry = LocalTraceSpan(
            self._now(),
            trace_id,
            span_id,
            operation.strip(),
            plugin_id,
            duration_ms,
            _redact(attributes or {}),
        )
        with self._lock:
            self._traces.append(entry)
            del self._traces[: max(0, len(self._traces) - self._max_records)]

    def metric(
        self,
        name: str,
        value: float,
        plugin_id: str,
        attributes: dict[str, object] | None = None,
    ) -> None:
        if not name.strip():
            raise ValueError("metric name is required")
        entry = LocalMetric(
            self._now(), name.strip(), float(value), plugin_id, _redact(attributes or {})
        )
        with self._lock:
            self._metrics.append(entry)
            del self._metrics[: max(0, len(self._metrics) - self._max_records)]

    def logs(self, *, limit: int = 100) -> tuple[dict[str, Any], ...]:
        return tuple(asdict(item) for item in self._logs[-self._limit(limit) :])

    def traces(self, *, limit: int = 100) -> tuple[dict[str, Any], ...]:
        return tuple(asdict(item) for item in self._traces[-self._limit(limit) :])

    def metrics(self, *, limit: int = 100) -> tuple[dict[str, Any], ...]:
        return tuple(asdict(item) for item in self._metrics[-self._limit(limit) :])

    @staticmethod
    def _limit(limit: int) -> int:
        if not 1 <= limit <= 1000:
            raise ValueError("observability limit must be between 1 and 1000")
        return limit


class LocalObservability:
    """Namespaced local telemetry facade intended for plugin consumers.

    The facade owns the plugin identity, so extensions cannot accidentally emit
    records attributed to another plugin. It deliberately has no exporter or
    network dependency; the host decides how the shared local buffer is read.
    """

    def __init__(self, plugin_id: str, buffer: LocalObservabilityBuffer) -> None:
        if not plugin_id.strip():
            raise ValueError("plugin_id must be non-empty")
        self.plugin_id = plugin_id
        self.buffer = buffer

    def log(
        self,
        level: str,
        message: str,
        attributes: dict[str, object] | None = None,
    ) -> None:
        self.buffer.log(level, message, self.plugin_id, attributes)

    def metric(
        self,
        name: str,
        value: float,
        attributes: dict[str, object] | None = None,
    ) -> None:
        self.buffer.metric(name, value, self.plugin_id, attributes)

    @contextmanager
    def span(
        self,
        operation: str,
        attributes: dict[str, object] | None = None,
    ) -> Any:
        trace_id = uuid4().hex
        span_id = uuid4().hex[:16]
        started = monotonic()
        try:
            yield trace_id, span_id
        finally:
            self.buffer.trace(
                trace_id,
                span_id,
                operation,
                self.plugin_id,
                (monotonic() - started) * 1000,
                attributes,
            )
