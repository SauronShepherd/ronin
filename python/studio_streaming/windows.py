"""Bounded event-time windowing for streaming micro-batches."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import StreamRecord


@dataclass(frozen=True, order=True, slots=True)
class EventTimeWindow:
    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("event-time window bounds are invalid")


@dataclass(frozen=True, slots=True)
class WindowedBatch:
    windows: tuple[tuple[EventTimeWindow, tuple[StreamRecord, ...]], ...]
    watermark_ms: int | None
    late_records: tuple[StreamRecord, ...]


def window_records(
    records: tuple[StreamRecord, ...], *, window_ms: int, allowed_lateness_ms: int = 0,
    previous_watermark_ms: int | None = None,
) -> WindowedBatch:
    """Assign timestamped records to fixed windows and classify late records."""
    if window_ms < 1 or allowed_lateness_ms < 0:
        raise ValueError("window size must be positive and lateness must be non-negative")
    timestamped = tuple(record for record in records if record.timestamp_ms is not None)
    if not timestamped:
        return WindowedBatch((), previous_watermark_ms, ())
    timestamps = tuple(record.timestamp_ms for record in timestamped if record.timestamp_ms is not None)
    maximum = max(timestamps)
    baseline = previous_watermark_ms if previous_watermark_ms is not None else 0
    watermark = max(maximum - allowed_lateness_ms, baseline)
    late_values: list[StreamRecord] = []
    for record in timestamped:
        timestamp = record.timestamp_ms
        if timestamp is not None and timestamp < baseline:
            late_values.append(record)
    late = tuple(late_values)
    grouped: dict[EventTimeWindow, list[StreamRecord]] = {}
    for record in timestamped:
        if record in late:
            continue
        timestamp = record.timestamp_ms
        if timestamp is None:
            continue
        start = (timestamp // window_ms) * window_ms
        grouped.setdefault(EventTimeWindow(start, start + window_ms), []).append(record)
    windows = tuple((key, tuple(sorted(value, key=lambda item: (item.partition, item.offset)))) for key, value in sorted(grouped.items()))
    return WindowedBatch(windows, watermark, late)


__all__ = ["EventTimeWindow", "WindowedBatch", "window_records"]
