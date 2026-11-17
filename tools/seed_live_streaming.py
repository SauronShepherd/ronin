"""Seed isolated live Kafka journeys with valid and poison records."""

from __future__ import annotations

import http.client
import json
import os
from importlib import import_module
from pathlib import Path
from urllib.parse import urlsplit

from confluent_kafka import Producer
from studio_streaming import (
    SqliteStreamCheckpointStore,
    StreamDefinition,
    StreamRuntimeBinding,
    StreamSchemaField,
    StreamSinkDefinition,
    StreamSourceDefinition,
)
from studio_streaming.kafka import MAX_KAFKA_RECORD_BYTES


def _required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value or value != value.strip():
        raise SystemExit(f"{name} must be set to a non-empty value")
    return value


def _positive_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise SystemExit(f"{name} must be an integer") from exc
    if value < 1:
        raise SystemExit(f"{name} must be at least 1")
    return value


def main() -> int:
    workspace_id = _required("RONIN_WORKSPACE_ID")
    database = Path(_required("RONIN_DB")).expanduser().resolve()
    bootstrap = _required("RONIN_LIVE_STREAMING_BOOTSTRAP")
    api = urlsplit(_required("RONIN_LIVE_API_URL"))
    if not api.hostname or api.port is None:
        raise SystemExit("RONIN_LIVE_API_URL must include a host and port")
    token = _required("RONIN_LIVE_API_TOKEN")
    replication_factor = _positive_int("RONIN_LIVE_STREAMING_REPLICATION_FACTOR", 1)
    backpressure_records = _positive_int("RONIN_LIVE_BACKPRESSURE_RECORDS", 256)
    topic = "ronin-live-events"
    poison_topic = "ronin-live-poison-events"
    oversized_topic = "ronin-live-oversized-events"
    recovery_topic = "ronin-live-recovery-events"
    partitioned_topic = "ronin-live-partitioned-events"
    fault_topic = "ronin-live-fault-events"
    sustained_topic = "ronin-live-sustained-events"
    backpressure_topic = "ronin-live-backpressure-events"
    near_record_limit_topic = "ronin-live-near-record-limit-events"
    near_batch_limit_topic = "ronin-live-near-batch-limit-events"
    over_batch_limit_topic = "ronin-live-over-batch-limit-events"
    multi_broker_topic = "ronin-live-multi-broker-events"
    stream_id = "events/main"
    poison_stream_id = "events/poison"
    oversized_stream_id = "events/oversized"
    partitioned_stream_id = "events/partitioned"

    kafka_admin = import_module("confluent_kafka.admin")
    admin = kafka_admin.AdminClient({"bootstrap.servers": bootstrap})
    for topic_name, num_partitions, topic_config in (
        (topic, 1, {}),
        (poison_topic, 1, {}),
        (oversized_topic, 1, {"max.message.bytes": str(MAX_KAFKA_RECORD_BYTES * 2)}),
        (recovery_topic, 1, {}),
        (partitioned_topic, 2, {}),
        (fault_topic, 1, {}),
        (sustained_topic, 2, {}),
        (backpressure_topic, 2, {}),
        (near_record_limit_topic, 1, {"max.message.bytes": str(MAX_KAFKA_RECORD_BYTES * 2)}),
        (near_batch_limit_topic, 1, {"max.message.bytes": str(MAX_KAFKA_RECORD_BYTES * 2)}),
        (over_batch_limit_topic, 1, {"max.message.bytes": str(MAX_KAFKA_RECORD_BYTES * 2)}),
        (multi_broker_topic, 1, {}),
    ):
        results = admin.create_topics(
            [
                kafka_admin.NewTopic(
                    topic_name,
                    num_partitions=num_partitions,
                    replication_factor=replication_factor,
                    config=topic_config,
                )
            ]
        )
        try:
            results[topic_name].result(timeout=20)
        except Exception as exc:
            # The fixture is intended for a newly created ephemeral broker.
            # Avoid accepting arbitrary creation errors as already existing.
            if "TOPIC_ALREADY_EXISTS" not in str(exc):
                raise SystemExit("Could not create the live Kafka qualification topic") from exc

    producer = Producer(
        {
            "bootstrap.servers": bootstrap,
            "message.max.bytes": MAX_KAFKA_RECORD_BYTES * 2,
        }
    )
    for index in range(5):
        producer.produce(
            topic,
            key=f"ronin-live-{index}",
            value=json.dumps({"event": f"qualification-{index}"}),
        )
    producer.produce(poison_topic, key="ronin-live-poison-1", value=b"{invalid-json")
    oversized = json.dumps({"event": "x" * MAX_KAFKA_RECORD_BYTES}).encode("utf-8")
    if len(oversized) <= MAX_KAFKA_RECORD_BYTES:
        raise SystemExit("The live oversized Kafka fixture must exceed Ronin's record cap")
    producer.produce(oversized_topic, key="ronin-live-oversized-1", value=oversized)

    def event_payload(target_bytes: int, fill: str) -> bytes:
        empty = json.dumps({"event": ""}, separators=(",", ":")).encode("utf-8")
        payload = json.dumps(
            {"event": fill * (target_bytes - len(empty))},
            separators=(",", ":"),
        ).encode("utf-8")
        if len(payload) != target_bytes:
            raise SystemExit("The live Kafka byte-boundary fixture was sized incorrectly")
        return payload

    near_record = event_payload(MAX_KAFKA_RECORD_BYTES - 1024, "r")
    producer.produce(
        near_record_limit_topic,
        key="ronin-live-near-record-1",
        value=near_record,
    )
    near_batch = event_payload(1_000_000, "b")
    for index in range(8):
        producer.produce(
            near_batch_limit_topic,
            key=f"ronin-live-near-batch-{index}",
            value=near_batch,
        )
    for index in range(9):
        producer.produce(
            over_batch_limit_topic,
            key=f"ronin-live-over-batch-{index}",
            value=near_batch,
        )
    producer.produce(
        recovery_topic,
        key="ronin-live-recovery-1",
        value=json.dumps({"event": "recovered"}),
    )
    for index in range(5):
        producer.produce(
            multi_broker_topic,
            key=f"ronin-live-multi-broker-{index}",
            value=json.dumps({"event": f"multi-broker-{index}"}),
        )
    for index in range(12):
        producer.produce(
            partitioned_topic,
            partition=index % 2,
            key=f"ronin-live-partitioned-{index}",
            value=json.dumps({"event": f"partitioned-{index}"}),
        )
    for index in range(64):
        producer.produce(
            sustained_topic,
            partition=index % 2,
            key=f"ronin-live-sustained-{index}",
            value=json.dumps({"event": f"sustained-{index}"}),
        )
    for index in range(backpressure_records):
        producer.produce(
            backpressure_topic,
            partition=index % 2,
            key=f"ronin-live-backpressure-{index}",
            value=json.dumps({"event": f"backpressure-{index:04d}"}),
        )
    producer.produce(fault_topic, key="ronin-live-fault-0", value=json.dumps({"event": "fault-0"}))
    if producer.flush(15) != 0:
        raise SystemExit("Kafka did not acknowledge the live qualification record")

    connection = http.client.HTTPConnection(api.hostname, api.port, timeout=5)
    body = {
        "connector_id": "kafka",
        "id": "live-kafka",
        "name": "Live qualification Kafka",
        "options": {"bootstrap.servers": bootstrap},
        "secret_refs": {},
    }
    try:
        connection.request(
            "POST",
            f"/v1/workspaces/{workspace_id}/connections",
            body=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        response.read()
        if response.status != 201:
            raise SystemExit(
                f"Could not register the Kafka fixture connection (HTTP {response.status})"
            )
    finally:
        connection.close()

    schema = (StreamSchemaField("event", "string", nullable=False),)
    definition = StreamDefinition(
        id=stream_id,
        name="Live qualification events",
        source=StreamSourceDefinition("live-kafka", topic, (0,)),
        sink=StreamSinkDefinition("table", "live-qualification-events"),
        schema=schema,
        runtime=StreamRuntimeBinding("local", batch_limit=2, timeout_seconds=1.0),
    )
    poison_definition = StreamDefinition(
        id=poison_stream_id,
        name="Live poison-message qualification",
        source=StreamSourceDefinition("live-kafka", poison_topic, (0,)),
        sink=StreamSinkDefinition("table", "live-poison-events"),
        schema=schema,
        runtime=StreamRuntimeBinding("local", batch_limit=1, timeout_seconds=1.0),
    )
    oversized_definition = StreamDefinition(
        id=oversized_stream_id,
        name="Live oversized-message recovery qualification",
        source=StreamSourceDefinition("live-kafka", oversized_topic, (0,)),
        sink=StreamSinkDefinition("table", "live-oversized-events"),
        schema=schema,
        runtime=StreamRuntimeBinding("local", batch_limit=1, timeout_seconds=1.0),
    )
    partitioned_definition = StreamDefinition(
        id=partitioned_stream_id,
        name="Live partitioned bounded streaming qualification",
        source=StreamSourceDefinition("live-kafka", partitioned_topic, (0, 1)),
        sink=StreamSinkDefinition("table", "live-partitioned-events"),
        schema=schema,
        # A fresh consumer needs enough time to discover the second partition
        # after the first partition has been drained by the prior micro-batch.
        runtime=StreamRuntimeBinding("local", batch_limit=2, timeout_seconds=2.0),
    )
    store = SqliteStreamCheckpointStore(database)
    store.commit_stream_bundle_import(
        workspace_id,
        (definition, poison_definition, oversized_definition, partitioned_definition),
        {
            stream_id: "reset",
            poison_stream_id: "reset",
            oversized_stream_id: "reset",
            partitioned_stream_id: "reset",
        },
    )
    print(
        "Seeded valid/poison/oversized/recovery/multi-broker topics, a two-partition topic, "
        f"replication factor {replication_factor}, connection, and durable stream definitions."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
