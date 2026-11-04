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


def main() -> int:
    workspace_id = _required("RONIN_WORKSPACE_ID")
    database = Path(_required("RONIN_DB")).expanduser().resolve()
    bootstrap = _required("RONIN_LIVE_STREAMING_BOOTSTRAP")
    api = urlsplit(_required("RONIN_LIVE_API_URL"))
    if not api.hostname or api.port is None:
        raise SystemExit("RONIN_LIVE_API_URL must include a host and port")
    token = _required("RONIN_LIVE_API_TOKEN")
    topic = "ronin-live-events"
    poison_topic = "ronin-live-poison-events"
    oversized_topic = "ronin-live-oversized-events"
    recovery_topic = "ronin-live-recovery-events"
    stream_id = "events/main"
    poison_stream_id = "events/poison"
    oversized_stream_id = "events/oversized"

    kafka_admin = import_module("confluent_kafka.admin")
    admin = kafka_admin.AdminClient({"bootstrap.servers": bootstrap})
    for topic_name, topic_config in (
        (topic, {}),
        (poison_topic, {}),
        (oversized_topic, {"max.message.bytes": str(MAX_KAFKA_RECORD_BYTES * 2)}),
        (recovery_topic, {}),
    ):
        results = admin.create_topics(
            [
                kafka_admin.NewTopic(
                    topic_name,
                    num_partitions=1,
                    replication_factor=1,
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
    producer.produce(
        recovery_topic,
        key="ronin-live-recovery-1",
        value=json.dumps({"event": "recovered"}),
    )
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
    store = SqliteStreamCheckpointStore(database)
    store.commit_stream_bundle_import(
        workspace_id,
        (definition, poison_definition, oversized_definition),
        {stream_id: "reset", poison_stream_id: "reset", oversized_stream_id: "reset"},
    )
    print("Seeded valid/poison broker topics, connection, and durable stream definitions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
