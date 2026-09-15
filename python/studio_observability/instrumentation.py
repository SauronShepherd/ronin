"""Provider-neutral execution instrumentation over the telemetry store contract."""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic
from typing import TypeVar

from studio_orchestrator import Instant

from .contracts import MetricPoint, TelemetryEvent

T = TypeVar("T")


def instrument_execution(
    operation: str,
    action: Callable[[], T],
    *,
    record_metric: Callable[[MetricPoint], object],
    record_event: Callable[[TelemetryEvent], object],
    observed_at: Instant,
) -> T:
    """Execute an action and emit success/failure telemetry at one boundary."""
    if not operation or operation != operation.strip():
        raise ValueError("operation must be non-empty and trimmed")
    started = monotonic()
    try:
        result = action()
    except Exception as exc:
        record_event(TelemetryEvent(
            f"execution.{operation}.failed", "error", observed_at, str(exc), (("operation", operation),)
        ))
        raise
    elapsed_ms = min(int((monotonic() - started) * 1000), 86_400_000)
    record_metric(MetricPoint(
        f"execution.{operation}.duration_ms", float(elapsed_ms), "milliseconds", "gauge", observed_at,
        (("operation", operation), ("status", "succeeded")),
    ))
    return result


__all__ = ["instrument_execution"]
