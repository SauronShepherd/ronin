"""Kafka JSON micro-batch source with Ronin-owned durable offsets."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .contracts import StreamBatch, StreamCheckpoint, StreamPosition, StreamRecord


class KafkaDependencyError(RuntimeError):
    """Raised when the optional confluent-kafka runtime is unavailable."""


def _kafka() -> tuple[Any, Any, int, int]:
    try:
        from confluent_kafka import Consumer, KafkaError, OFFSET_BEGINNING, TopicPartition
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise KafkaDependencyError(
            "Kafka streaming support requires the optional Ronin streaming dependencies"
        ) from exc
    return Consumer, TopicPartition, KafkaError._PARTITION_EOF, OFFSET_BEGINNING


def _text(value: str, name: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    return value


class KafkaJsonSource:
    """Consume explicit Kafka partitions without broker-owned offset commits.

    Ronin's StreamCheckpointStore is authoritative. The adapter therefore disables
    auto commit and auto offset storage, manually assigns known partitions, and starts
    each partition at `last_processed_offset + 1` (or Kafka beginning when unseen).
    """

    def __init__(
        self,
        *,
        bootstrap_servers: str,
        topic: str,
        partitions: tuple[int, ...],
        group_id: str = "ronin-reference-stream",
        client_id: str = "ronin-streaming",
        config: Mapping[str, object] | None = None,
    ) -> None:
        self._bootstrap_servers = _text(bootstrap_servers, "Kafka bootstrap_servers")
        self._topic = _text(topic, "Kafka topic")
        self._group_id = _text(group_id, "Kafka group_id")
        self._client_id = _text(client_id, "Kafka client_id")
        canonical = tuple(sorted(partitions))
        if not canonical or any(value < 0 for value in canonical):
            raise ValueError("Kafka partitions must contain non-negative partition ids")
        if len(canonical) != len(set(canonical)):
            raise ValueError("Kafka partitions must be unique")
        self._partitions = canonical
        extra = dict(config or {})
        forbidden = {
            "bootstrap.servers",
            "group.id",
            "client.id",
            "enable.auto.commit",
            "enable.auto.offset.store",
        }
        if forbidden & set(extra):
            raise ValueError("Kafka config must not override Ronin-owned identity/offset settings")
        self._config = extra

    def poll(
        self,
        checkpoint: StreamCheckpoint,
        *,
        limit: int,
        timeout_seconds: float,
    ) -> StreamBatch:
        if limit < 1 or limit > 100_000:
            raise ValueError("Kafka poll limit must be between 1 and 100000")
        if timeout_seconds < 0 or timeout_seconds > 300:
            raise ValueError("Kafka poll timeout_seconds must be in [0, 300]")
        Consumer, TopicPartition, partition_eof, offset_beginning = _kafka()
        config: dict[str, object] = {
            "bootstrap.servers": self._bootstrap_servers,
            "group.id": self._group_id,
            "client.id": self._client_id,
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
            "auto.offset.reset": "earliest",
            **self._config,
        }
        consumer = Consumer(config)
        try:
            assignments = []
            for partition in self._partitions:
                previous = checkpoint.offset_for(partition)
                offset = offset_beginning if previous is None else previous + 1
                assignments.append(TopicPartition(self._topic, partition, offset))
            consumer.assign(assignments)
            messages = consumer.consume(num_messages=limit, timeout=timeout_seconds)
            records: list[StreamRecord] = []
            latest = {item.partition: item.offset for item in checkpoint.positions}
            for message in messages:
                error = message.error()
                if error is not None:
                    if error.code() == partition_eof:
                        continue
                    raise RuntimeError(f"Kafka consume error: {error}")
                raw = message.value()
                if raw is None:
                    raise ValueError("Kafka JSON source does not accept null message values")
                try:
                    decoded = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                    value = json.loads(decoded)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ValueError("Kafka message value is not valid UTF-8 JSON") from exc
                if not isinstance(value, dict):
                    raise ValueError("Kafka JSON source requires object message values")
                key_raw = message.key()
                if key_raw is None:
                    key = None
                elif isinstance(key_raw, bytes):
                    try:
                        key = key_raw.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        raise ValueError("Kafka message key must be UTF-8 when present") from exc
                else:
                    key = str(key_raw)
                timestamp_type, timestamp_value = message.timestamp()
                del timestamp_type
                timestamp_ms = (
                    None if timestamp_value is None or timestamp_value < 0 else int(timestamp_value)
                )
                partition = int(message.partition())
                offset = int(message.offset())
                records.append(StreamRecord(partition, offset, timestamp_ms, key, value))
                latest[partition] = max(latest.get(partition, -1), offset)
            if not records:
                return StreamBatch((), checkpoint)
            next_checkpoint = StreamCheckpoint(
                tuple(StreamPosition(partition, offset) for partition, offset in latest.items())
            )
            return StreamBatch(tuple(records), next_checkpoint)
        finally:
            consumer.close()


__all__ = ("KafkaDependencyError", "KafkaJsonSource")
