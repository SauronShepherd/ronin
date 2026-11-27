"""Kafka JSON micro-batch source with Ronin-owned durable offsets."""

from __future__ import annotations

import json
import time
from collections import OrderedDict
from collections.abc import Mapping
from importlib import import_module
from typing import Any

from .contracts import StreamBatch, StreamCheckpoint, StreamPosition, StreamRecord

MAX_KAFKA_RECORD_BYTES = 1_048_576
MAX_KAFKA_BATCH_BYTES = 8_388_608
_KAFKA_PROTOCOL_OVERHEAD_BYTES = 512
_KAFKA_METADATA_PROBE_TTL_SECONDS = 5.0
_KAFKA_METADATA_PROBE_CACHE_LIMIT = 256
_KAFKA_PARTIAL_BATCH_GRACE_SECONDS = 0.05
_kafka_metadata_probe_cache: OrderedDict[tuple[str, str, tuple[int, ...]], float] = OrderedDict()


def _probe_kafka_metadata(
    consumer: Any,
    *,
    bootstrap_servers: str,
    topic: str,
    partitions: tuple[int, ...],
    timeout_seconds: float,
) -> None:
    """Probe broker availability, reusing only recent successful metadata probes.

    A fresh source is created for each bounded HTTP cycle. Repeating a metadata
    round-trip for every cycle can dominate throughput, so successful probes are
    reused briefly. Failures are never cached, and every cycle still calls
    ``consume`` so a broker failure remains observable immediately.
    """

    list_topics = getattr(consumer, "list_topics", None)
    if not callable(list_topics):
        return
    key = (bootstrap_servers, topic, partitions)
    now = time.monotonic()
    cached_at = _kafka_metadata_probe_cache.get(key)
    if cached_at is not None and now - cached_at < _KAFKA_METADATA_PROBE_TTL_SECONDS:
        _kafka_metadata_probe_cache.move_to_end(key)
        return
    list_topics(timeout=max(float(timeout_seconds), 0.1))
    _kafka_metadata_probe_cache[key] = time.monotonic()
    _kafka_metadata_probe_cache.move_to_end(key)
    while len(_kafka_metadata_probe_cache) > _KAFKA_METADATA_PROBE_CACHE_LIMIT:
        _kafka_metadata_probe_cache.popitem(last=False)


class KafkaDependencyError(RuntimeError):
    """Raised when the optional confluent-kafka runtime is unavailable."""


class KafkaInputRejected(ValueError):
    """Raised when a broker record violates Ronin's bounded JSON input contract."""


def _kafka() -> tuple[Any, Any, int, int]:
    try:
        kafka = import_module("confluent_kafka")
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise KafkaDependencyError(
            "Kafka streaming support requires the optional Ronin streaming dependencies"
        ) from exc
    return (
        kafka.Consumer,
        kafka.TopicPartition,
        kafka.KafkaError._PARTITION_EOF,
        kafka.OFFSET_BEGINNING,
    )


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
            # Keep transport buffering under Ronin's byte budgets. Allowing a
            # connection option to override these would make API batch limits
            # insufficient to bound memory before JSON decoding.
            "fetch.max.bytes",
            "max.partition.fetch.bytes",
            "receive.message.max.bytes",
            "queued.max.messages.kbytes",
        }
        if forbidden & set(extra):
            raise ValueError("Kafka config must not override Ronin-owned identity/offset settings")
        self._config = extra
        self._consumer: Any | None = None
        self._consumer_checkpoint: StreamCheckpoint | None = None
        self._partition_eof: int | None = None

    def _ensure_consumer(
        self,
        checkpoint: StreamCheckpoint,
        *,
        timeout_seconds: float,
    ) -> tuple[Any, int]:
        if self._consumer is not None:
            if self._partition_eof is None:
                raise RuntimeError("Kafka consumer session lost its partition EOF marker")
            _Consumer, TopicPartition, _partition_eof, _offset_beginning = _kafka()
            if checkpoint != self._consumer_checkpoint:
                assignments = []
                for partition in self._partitions:
                    previous = checkpoint.offset_for(partition)
                    offset = _offset_beginning if previous is None else previous + 1
                    assignments.append(TopicPartition(self._topic, partition, offset))
                try:
                    # Reassign only when Ronin's durable checkpoint changed;
                    # retries and resets still force an explicit seek.
                    self._consumer.assign(assignments)
                except Exception:
                    self.close()
                    raise
            self._consumer_checkpoint = checkpoint
            return self._consumer, self._partition_eof

        self.close()
        Consumer, TopicPartition, partition_eof, offset_beginning = _kafka()
        config: dict[str, object] = {
            "bootstrap.servers": self._bootstrap_servers,
            "group.id": self._group_id,
            "client.id": self._client_id,
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
            "fetch.max.bytes": MAX_KAFKA_BATCH_BYTES,
            "max.partition.fetch.bytes": MAX_KAFKA_RECORD_BYTES + _KAFKA_PROTOCOL_OVERHEAD_BYTES,
            "receive.message.max.bytes": MAX_KAFKA_BATCH_BYTES + _KAFKA_PROTOCOL_OVERHEAD_BYTES,
            "queued.max.messages.kbytes": (MAX_KAFKA_BATCH_BYTES // 1024) + 1024,
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
            # A disconnected broker can make librdkafka's bounded consume call
            # return an empty batch after its timeout instead of surfacing the
            # transport failure. Probe metadata once per consumer session so the
            # runtime reports provider unavailability rather than false idle.
            _probe_kafka_metadata(
                consumer,
                bootstrap_servers=self._bootstrap_servers,
                topic=self._topic,
                partitions=self._partitions,
                timeout_seconds=timeout_seconds,
            )
        except Exception:
            consumer.close()
            raise

        self._consumer = consumer
        self._consumer_checkpoint = checkpoint
        self._partition_eof = partition_eof
        return consumer, partition_eof

    def close(self) -> None:
        """Close the broker consumer owned by this source, if it is open."""

        consumer, self._consumer = self._consumer, None
        self._consumer_checkpoint = None
        self._partition_eof = None
        if consumer is not None:
            consumer.close()

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
        consumer, partition_eof = self._ensure_consumer(
            checkpoint,
            timeout_seconds=timeout_seconds,
        )
        try:
            records: list[StreamRecord] = []
            batch_bytes = 0
            latest = {item.partition: item.offset for item in checkpoint.positions}
            deadline = time.monotonic() + timeout_seconds
            first_poll = True
            partial_batch_grace_used = False
            while len(records) < limit:
                # Once a fetch has yielded records, only drain data already
                # available to this consumer. Waiting the remaining provider
                # timeout after a partial fetch turns a bounded micro-batch
                # into repeated underfilled API calls when another assigned
                # partition is already queued locally.
                remaining = (
                    timeout_seconds
                    if first_poll and not records
                    else 0.0
                    if records
                    else max(0.0, deadline - time.monotonic())
                )
                is_first_poll = first_poll
                first_poll = False
                if remaining <= 0:
                    if is_first_poll:
                        pass
                    elif not records or partial_batch_grace_used:
                        break
                    else:
                        # A bounded consume can return a partial batch exactly
                        # at the deadline while additional records are already
                        # queued by another partition. Give that queued data
                        # one short, non-blocking grace window so small limits
                        # do not turn a sustained backlog into repeated
                        # underfilled API calls.
                        remaining = _KAFKA_PARTIAL_BATCH_GRACE_SECONDS
                        partial_batch_grace_used = True
                messages = consumer.consume(
                    num_messages=limit - len(records),
                    timeout=remaining,
                )
                for message in messages:
                    error = message.error()
                    if error is not None:
                        if error.code() == partition_eof:
                            continue
                        raise RuntimeError(f"Kafka consume error: {error}")
                    raw = message.value()
                    if raw is None:
                        raise KafkaInputRejected(
                            "Kafka JSON source does not accept null message values"
                        )
                    raw_bytes = raw if isinstance(raw, bytes) else str(raw).encode("utf-8")
                    if len(raw_bytes) > MAX_KAFKA_RECORD_BYTES:
                        raise KafkaInputRejected(
                            "Kafka JSON message exceeds the 1 MiB record limit"
                        )
                    batch_bytes += len(raw_bytes)
                    if batch_bytes > MAX_KAFKA_BATCH_BYTES:
                        raise KafkaInputRejected(
                            "Kafka JSON micro-batch exceeds the 8 MiB byte limit"
                        )
                    try:
                        value = json.loads(raw_bytes.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise KafkaInputRejected(
                            "Kafka message value is not valid UTF-8 JSON"
                        ) from exc
                    if not isinstance(value, dict):
                        raise KafkaInputRejected("Kafka JSON source requires object message values")
                    key_raw = message.key()
                    if key_raw is None:
                        key = None
                    elif isinstance(key_raw, bytes):
                        try:
                            key = key_raw.decode("utf-8")
                        except UnicodeDecodeError as exc:
                            raise KafkaInputRejected(
                                "Kafka message key must be UTF-8 when present"
                            ) from exc
                    else:
                        key = str(key_raw)
                    timestamp_type, timestamp_value = message.timestamp()
                    del timestamp_type
                    timestamp_ms = (
                        None
                        if timestamp_value is None or timestamp_value < 0
                        else int(timestamp_value)
                    )
                    partition = int(message.partition())
                    offset = int(message.offset())
                    records.append(StreamRecord(partition, offset, timestamp_ms, key, value))
                    latest[partition] = max(latest.get(partition, -1), offset)
                # Keep filling the bounded micro-batch while the provider
                # deadline permits it. A multi-partition fetch can return only
                # part of the requested limit even when more records are ready;
                # stopping after that first non-empty fetch needlessly turns a
                # limit=4 batch into one- or two-record batches and can starve
                # bounded supervisors under sustained backlog.
                # Do not stop immediately at the deadline after a partial
                # fetch.  The next loop iteration applies the bounded,
                # non-blocking grace window above once, allowing records that
                # arrived on another assigned partition to complete this
                # micro-batch without extending the provider wait unboundedly.
            if not records:
                return StreamBatch((), checkpoint)
            next_checkpoint = StreamCheckpoint(
                tuple(StreamPosition(partition, offset) for partition, offset in latest.items())
            )
            self._consumer_checkpoint = next_checkpoint
            return StreamBatch(tuple(records), next_checkpoint)
        except Exception:
            self.close()
            raise


__all__ = ("KafkaDependencyError", "KafkaInputRejected", "KafkaJsonSource")
