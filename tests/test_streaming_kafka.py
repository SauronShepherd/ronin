from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from studio_streaming import StreamCheckpoint
from studio_streaming import kafka as kafka_adapter
from studio_streaming.kafka import (
    MAX_KAFKA_BATCH_BYTES,
    MAX_KAFKA_RECORD_BYTES,
    KafkaInputRejected,
    KafkaJsonSource,
)


@dataclass(frozen=True)
class _TopicPartition:
    topic: str
    partition: int
    offset: int


class _Message:
    def __init__(self, value: bytes, offset: int) -> None:
        self._value = value
        self._offset = offset

    def error(self):
        return None

    def value(self):
        return self._value

    def key(self):
        return None

    def timestamp(self):
        return (0, 1_700_000_000_000)

    def partition(self):
        return 0

    def offset(self):
        return self._offset


class _Consumer:
    def __init__(self, messages: list[_Message]) -> None:
        self.messages = messages
        self.config = None
        self.assignments = None
        self.consume_args = None
        self.closed = False

    def assign(self, assignments) -> None:
        self.assignments = assignments

    def consume(self, *, num_messages: int, timeout: float):
        self.consume_args = (num_messages, timeout)
        return self.messages

    def close(self) -> None:
        self.closed = True


def _source(monkeypatch: pytest.MonkeyPatch, messages: list[_Message], *, config=None):
    consumer = _Consumer(messages)

    def consumer_type(settings):
        return _capture_config(consumer, settings)

    fake_kafka = SimpleNamespace(
        Consumer=consumer_type,
        TopicPartition=_TopicPartition,
        KafkaError=SimpleNamespace(_PARTITION_EOF=-191),
        OFFSET_BEGINNING=-2,
    )
    monkeypatch.setattr(kafka_adapter, "import_module", lambda _name: fake_kafka)
    source = KafkaJsonSource(
        bootstrap_servers="localhost:9092",
        topic="events",
        partitions=(0,),
        config=config,
    )
    return source, consumer


def _capture_config(consumer: _Consumer, settings: dict[str, object]) -> _Consumer:
    consumer.config = settings
    return consumer


def test_kafka_source_applies_ronin_owned_fetch_and_queue_budgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, consumer = _source(monkeypatch, [_Message(b'{"event":"ok"}', 0)])

    batch = source.poll(StreamCheckpoint(), limit=10, timeout_seconds=0.1)

    assert batch.records[0].value == {"event": "ok"}
    assert consumer.config["enable.auto.commit"] is False
    assert consumer.config["enable.auto.offset.store"] is False
    assert consumer.config["max.partition.fetch.bytes"] == MAX_KAFKA_RECORD_BYTES + 512
    assert consumer.config["fetch.max.bytes"] == MAX_KAFKA_BATCH_BYTES
    assert consumer.config["receive.message.max.bytes"] == MAX_KAFKA_BATCH_BYTES + 512
    assert consumer.config["queued.max.messages.kbytes"] * 1024 >= MAX_KAFKA_BATCH_BYTES
    assert consumer.assignments == [_TopicPartition("events", 0, -2)]
    assert consumer.consume_args == (10, 0.1)
    assert consumer.closed


@pytest.mark.parametrize(
    "setting",
    [
        "fetch.max.bytes",
        "max.partition.fetch.bytes",
        "receive.message.max.bytes",
        "queued.max.messages.kbytes",
    ],
)
def test_kafka_connection_cannot_override_memory_budgets(setting: str) -> None:
    with pytest.raises(ValueError, match="must not override"):
        KafkaJsonSource(
            bootstrap_servers="localhost:9092",
            topic="events",
            partitions=(0,),
            config={setting: 128 * 1024 * 1024},
        )


def test_kafka_source_rejects_record_over_one_mib_before_decoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, consumer = _source(
        monkeypatch,
        [_Message(b" " * (MAX_KAFKA_RECORD_BYTES + 1), 0)],
    )

    with pytest.raises(ValueError, match="1 MiB record limit"):
        source.poll(StreamCheckpoint(), limit=10, timeout_seconds=0.0)

    assert consumer.closed


@pytest.mark.parametrize("raw", [b"{invalid-json", b"[]", b"\xff"])
def test_kafka_source_rejects_poison_values(raw: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    source, consumer = _source(monkeypatch, [_Message(raw, 0)])

    with pytest.raises(KafkaInputRejected):
        source.poll(StreamCheckpoint(), limit=10, timeout_seconds=0.0)

    assert consumer.closed


def test_kafka_source_rejects_micro_batch_over_eight_mib(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = '{"v":"' + ("a" * (MAX_KAFKA_RECORD_BYTES - 8)) + '"}'
    raw = value.encode("utf-8")
    assert len(raw) == MAX_KAFKA_RECORD_BYTES
    messages = [_Message(raw, offset) for offset in range(8)]
    messages.append(_Message(b" ", 8))
    source, consumer = _source(monkeypatch, messages)

    with pytest.raises(ValueError, match="8 MiB byte limit"):
        source.poll(StreamCheckpoint(), limit=10, timeout_seconds=0.0)

    assert consumer.closed
