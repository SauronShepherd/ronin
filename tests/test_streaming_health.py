from types import SimpleNamespace

import pytest
from studio_core import SecretRef
from studio_streaming import (
    KafkaStreamingHealthReader,
    SqliteStreamCheckpointStore,
    StreamCheckpoint,
    StreamDefinition,
    StreamingUnavailable,
    StreamPosition,
    StreamRuntimeBinding,
    StreamSchemaField,
    StreamSinkDefinition,
    StreamSourceDefinition,
    stream_health,
)


def test_stream_health_reports_partition_lag():
    checkpoint = StreamCheckpoint((StreamPosition(0, 4), StreamPosition(1, 9)))
    health = stream_health("orders", checkpoint, latest_offsets={0: 5, 1: 9})
    assert health["lag"] == {"0": 1, "1": 0}
    assert health["total_lag"] == 1
    assert health["healthy"] is False


def test_stream_health_rejects_invalid_latest_offsets():
    checkpoint = StreamCheckpoint(())
    with pytest.raises(ValueError, match="latest offset"):
        stream_health("orders", checkpoint, latest_offsets={0: -2})


def test_stream_health_counts_unseen_partition_from_offset_minus_one():
    health = stream_health("orders", StreamCheckpoint(), latest_offsets={2: 3})
    assert health["lag"] == {"2": 4}
    assert health["total_lag"] == 4


def test_stream_health_serializes_partitions_in_deterministic_order() -> None:
    health = stream_health("orders", StreamCheckpoint(), latest_offsets={3: 0, 1: 2, 2: 1})
    assert tuple(health["lag"]) == ("1", "2", "3")


def _stream_definition() -> StreamDefinition:
    return StreamDefinition(
        id="events/main",
        name="Live events",
        source=StreamSourceDefinition("kafka-live", "events", (0, 1)),
        sink=StreamSinkDefinition("table", "events-output"),
        schema=(StreamSchemaField("event", "json"),),
        runtime=StreamRuntimeBinding("local", batch_limit=10),
    )


def test_kafka_health_reader_uses_persisted_definition_and_live_watermarks(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import studio_streaming.health as streaming_health

    store = SqliteStreamCheckpointStore(tmp_path / "streams.sqlite3")
    store.commit_stream_bundle_import(
        "workspace-1", (_stream_definition(),), {"events/main": "reset"}
    )
    topic_partitions: list[tuple[str, int]] = []

    class Consumer:
        def __init__(self, config):
            assert config["bootstrap.servers"] == "127.0.0.1:19092"
            assert config["enable.auto.commit"] is False
            assert config["sasl.password"] == "secret-value"
            self.closed = False

        def get_watermark_offsets(self, topic_partition, *, timeout, cached):
            assert timeout == 3
            assert cached is False
            topic_partitions.append(topic_partition)
            return (0, 1) if topic_partition[1] == 0 else (0, 0)

        def close(self):
            self.closed = True

    consumer: Consumer | None = None

    def factory(config):
        nonlocal consumer
        consumer = Consumer(config)
        return consumer

    monkeypatch.setattr(
        streaming_health,
        "_kafka",
        lambda: (Consumer, lambda topic, partition: (topic, partition), -191, -2),
    )
    connection = SimpleNamespace(
        connector_id="kafka",
        options=(("bootstrap.servers", "127.0.0.1:19092"),),
        secret_refs=(("sasl.password", SecretRef("secret://env/KAFKA_PASSWORD")),),
    )
    reader = KafkaStreamingHealthReader(
        store,
        lambda _workspace, _connection_id: connection,
        lambda _reference: "secret-value",
        consumer_factory=factory,
    )

    result = reader.health("workspace-1", "events/main")

    assert result["source_status"] == "available"
    assert result["status"] == "lagging"
    assert result["lag"] == {"0": 1, "1": 0}
    assert result["empty_partitions"] == ["1"]
    assert result["observed_at"].endswith("Z")
    assert "T" in result["observed_at"]
    assert "secret-value" not in str(result)
    assert topic_partitions == [("events", 0), ("events", 1)]
    assert consumer is not None
    assert consumer.closed


def test_kafka_health_reader_reports_unknown_stream_as_not_found(tmp_path) -> None:
    reader = KafkaStreamingHealthReader(
        SqliteStreamCheckpointStore(tmp_path / "streams.sqlite3"),
        lambda _workspace, _connection: None,
        lambda _reference: "secret",
    )

    with pytest.raises(KeyError, match="stream not found"):
        reader.health("workspace-1", "missing")


def test_kafka_health_reader_redacts_broker_exception(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import studio_streaming.health as streaming_health

    store = SqliteStreamCheckpointStore(tmp_path / "streams.sqlite3")
    store.commit_stream_bundle_import(
        "workspace-1", (_stream_definition(),), {"events/main": "reset"}
    )

    class Consumer:
        def __init__(self, _config):
            pass

        def get_watermark_offsets(self, *_args, **_kwargs):
            raise RuntimeError("broker password=do-not-leak")

        def close(self):
            pass

    monkeypatch.setattr(
        streaming_health,
        "_kafka",
        lambda: (Consumer, lambda topic, partition: (topic, partition), -191, -2),
    )
    connection = SimpleNamespace(
        connector_id="kafka",
        options=(("bootstrap.servers", "127.0.0.1:19092"),),
        secret_refs=(),
    )
    reader = KafkaStreamingHealthReader(
        store,
        lambda _workspace, _connection: connection,
        lambda _reference: "secret",
        consumer_factory=Consumer,
    )

    with pytest.raises(
        StreamingUnavailable, match="Kafka broker health could not be read"
    ) as error:
        reader.health("workspace-1", "events/main")
    assert "do-not-leak" not in str(error.value)
