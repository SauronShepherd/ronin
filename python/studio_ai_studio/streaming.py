"""Bounded SSE parsing and forwarding primitives for AI Studio."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Iterator
from dataclasses import dataclass


class StreamLimitExceeded(RuntimeError):
    """The upstream stream exceeded configured memory or duration bounds."""


class StreamProtocolError(RuntimeError):
    """The upstream emitted invalid SSE data."""


@dataclass(frozen=True, slots=True)
class StreamLimits:
    max_event_bytes: int = 256 * 1024
    max_stream_bytes: int = 64 * 1024 * 1024
    max_events: int = 100_000

    def __post_init__(self) -> None:
        if self.max_event_bytes < 1 or self.max_stream_bytes < self.max_event_bytes:
            raise ValueError("invalid SSE byte limits")
        if self.max_events < 1:
            raise ValueError("max_events must be positive")


class BoundedEventQueue:
    def __init__(self, max_events: int = 256) -> None:
        if max_events < 1:
            raise ValueError("max_events must be positive")
        self._items: deque[bytes] = deque(maxlen=max_events)
        self._max_events = max_events

    def put(self, item: bytes) -> None:
        if len(self._items) >= self._max_events:
            raise StreamLimitExceeded("stream backpressure queue is full")
        self._items.append(item)

    def get(self) -> bytes | None:
        return self._items.popleft() if self._items else None

    def __len__(self) -> int:
        return len(self._items)


def parse_sse(chunks: Iterable[bytes], *, limits: StreamLimits | None = None) -> Iterator[bytes]:
    """Yield complete SSE events, preserving event bytes and rejecting overflow."""
    config = limits or StreamLimits()
    pending = bytearray()
    total = 0
    events = 0
    for chunk in chunks:
        if not isinstance(chunk, bytes):
            raise StreamProtocolError("SSE transport yielded non-bytes")
        total += len(chunk)
        if total > config.max_stream_bytes:
            raise StreamLimitExceeded("stream exceeded byte limit")
        pending.extend(chunk)
        if len(pending) > config.max_event_bytes:
            raise StreamLimitExceeded("SSE event exceeded byte limit")
        while b"\n\n" in pending:
            position = pending.index(b"\n\n") + 2
            event = bytes(pending[:position])
            del pending[:position]
            events += 1
            if events > config.max_events:
                raise StreamLimitExceeded("stream exceeded event limit")
            _validate_event(event)
            yield event
    if pending:
        raise StreamProtocolError("SSE stream ended with an incomplete event")


def _validate_event(event: bytes) -> None:
    if b"\x00" in event:
        raise StreamProtocolError("SSE event contains NUL")
    data_lines = [line[5:] for line in event.splitlines() if line.startswith(b"data:")]
    if not data_lines:
        raise StreamProtocolError("SSE event has no data field")


__all__ = [
    "BoundedEventQueue",
    "StreamLimitExceeded",
    "StreamLimits",
    "StreamProtocolError",
    "parse_sse",
]
