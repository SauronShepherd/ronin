"""Provider-neutral streaming health and lag projection."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from .checkpoint import SqliteStreamCheckpointStore
from .contracts import StreamCheckpoint
from .kafka import KafkaDependencyError, _kafka


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


class StreamingUnavailable(TimeoutError):
    """Raised when a configured stream cannot obtain live broker health."""


class KafkaStreamingHealthReader:
    """Read persisted stream intent and current Kafka watermarks without consuming data."""

    def __init__(
        self,
        checkpoints: SqliteStreamCheckpointStore,
        resolve_connection: Callable[[str, str], Any],
        resolve_secret: Callable[[Any], str],
        *,
        timeout_seconds: float = 3.0,
        consumer_factory: Callable[[Mapping[str, object]], Any] | None = None,
    ) -> None:
        if not 0 < timeout_seconds <= 30:
            raise ValueError("stream health timeout_seconds must be in (0, 30]")
        self._checkpoints = checkpoints
        self._resolve_connection = resolve_connection
        self._resolve_secret = resolve_secret
        self._timeout_seconds = timeout_seconds
        self._consumer_factory = consumer_factory

    def health(self, workspace_id: Any, stream_id: str) -> dict[str, object]:
        workspace_key = str(workspace_id)
        definition = self._checkpoints.get_definition(workspace_key, stream_id)
        if definition is None:
            raise KeyError(f"stream not found: {stream_id}")

        connection = self._resolve_connection(workspace_key, definition.source.connection_id)
        if connection.connector_id not in {"kafka", "apache.kafka"}:
            raise StreamingUnavailable("stream source connection is not a Kafka connection")
        options = dict(connection.options)
        try:
            secret_options = {
                name: self._resolve_secret(reference) for name, reference in connection.secret_refs
            }
        except Exception as exc:
            raise StreamingUnavailable("Kafka connection secrets could not be resolved") from exc
        bootstrap_servers = options.pop("bootstrap.servers", "").strip()
        if not bootstrap_servers:
            raise StreamingUnavailable("Kafka connection has no bootstrap.servers option")
        if "bootstrap.servers" in secret_options:
            raise StreamingUnavailable(
                "Kafka bootstrap.servers must be a non-secret connection option"
            )

        try:
            consumer_factory = self._consumer_factory
            if consumer_factory is None:
                Consumer, TopicPartition, _partition_eof, _offset_beginning = _kafka()
                consumer_factory = Consumer
            else:
                _Consumer, TopicPartition, _partition_eof, _offset_beginning = _kafka()
        except KafkaDependencyError as exc:
            raise StreamingUnavailable(str(exc)) from exc

        config: dict[str, object] = {
            **options,
            **secret_options,
            "bootstrap.servers": bootstrap_servers,
            "group.id": "ronin-stream-health",
            "client.id": "ronin-stream-health",
            "socket.timeout.ms": int(self._timeout_seconds * 1000),
            "allow.auto.create.topics": False,
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
        }
        consumer: Any | None = None
        try:
            consumer = consumer_factory(config)
            high_watermarks: dict[int, int] = {}
            for partition in definition.source.partitions:
                low, high = consumer.get_watermark_offsets(
                    TopicPartition(definition.source.resource, partition),
                    timeout=self._timeout_seconds,
                    cached=False,
                )
                if low < 0 or high < low:
                    raise StreamingUnavailable("Kafka returned invalid partition watermarks")
                # Kafka high watermark is exclusive; stream_health accepts the last
                # available offset, so an empty partition is represented as -1.
                high_watermarks[partition] = high - 1
            runtime_id = self._checkpoints.runtime_stream_id(workspace_key, stream_id)
            checkpoint = self._checkpoints.get(runtime_id)
            projection = stream_health(stream_id, checkpoint, latest_offsets=high_watermarks)
            projection.update(
                {
                    "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "source_status": "available",
                    "status": "healthy" if projection["healthy"] else "lagging",
                    "empty_partitions": sorted(
                        str(partition)
                        for partition, latest in high_watermarks.items()
                        if latest == -1
                    ),
                }
            )
            return projection
        except StreamingUnavailable:
            raise
        except Exception as exc:
            # Provider exception text can contain endpoints or credentials; keep
            # the public error stable and leave diagnostic detail to server logs.
            raise StreamingUnavailable("Kafka broker health could not be read") from exc
        finally:
            if consumer is not None:
                with suppress(Exception):
                    consumer.close()


__all__ = ("KafkaStreamingHealthReader", "StreamingUnavailable", "stream_health")
