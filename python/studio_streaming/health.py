"""Provider-neutral streaming health and lag projection."""

from __future__ import annotations

from .contracts import StreamCheckpoint


def stream_health(
    stream_id: str, checkpoint: StreamCheckpoint, *, latest_offsets: dict[int, int]
) -> dict[str, object]:
    """Return bounded, non-secret lag evidence for a stream."""
    if not stream_id or stream_id != stream_id.strip() or "\x00" in stream_id:
        raise ValueError("stream_id must be non-empty and trimmed")
    if len(latest_offsets) > 10_000:
        raise ValueError("latest_offsets is too large")
    lag: dict[str, int] = {}
    for partition, latest in sorted(latest_offsets.items()):
        if not isinstance(partition, int) or isinstance(partition, bool) or partition < 0:
            raise ValueError("latest offset partition must be a non-negative integer")
        if not isinstance(latest, int) or isinstance(latest, bool) or latest < -1:
            raise ValueError("latest offset must be an integer >= -1")
        committed = checkpoint.offset_for(partition)
        lag[str(partition)] = max(0, latest - (-1 if committed is None else committed))
    return {
        "stream_id": stream_id,
        "checkpoint_digest": checkpoint.digest,
        "partitions": len(latest_offsets),
        "lag": lag,
        "total_lag": sum(lag.values()),
        "healthy": all(value == 0 for value in lag.values()),
    }


__all__ = ("stream_health",)
