"""Produce a bounded live Kafka stream for supervisor-duration qualification."""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from importlib import import_module

from confluent_kafka import Producer


def _required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value or value != value.strip():
        raise SystemExit(f"{name} must be set to a non-empty value")
    return value


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise SystemExit(f"{name} must be between {minimum} and {maximum}")
    return value


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise SystemExit(f"{name} must be numeric") from exc
    if not minimum <= value <= maximum:
        raise SystemExit(f"{name} must be between {minimum} and {maximum}")
    return value


def _create_topic(bootstrap: str, topic: str, replication_factor: int) -> None:
    kafka_admin = import_module("confluent_kafka.admin")
    admin = kafka_admin.AdminClient({"bootstrap.servers": bootstrap})
    result = admin.create_topics(
        [
            kafka_admin.NewTopic(
                topic,
                num_partitions=2,
                replication_factor=replication_factor,
            )
        ]
    )
    try:
        result[topic].result(timeout=20)
    except Exception as exc:
        if "TOPIC_ALREADY_EXISTS" not in str(exc):
            raise RuntimeError("could not create the supervisor soak Kafka topic") from exc


def main() -> int:
    bootstrap = _required("RONIN_LIVE_STREAMING_BOOTSTRAP")
    topic = os.environ.get("RONIN_LIVE_SUPERVISOR_SOAK_TOPIC", "ronin-live-supervisor-soak-events")
    duration_seconds = _bounded_int("RONIN_LIVE_SUPERVISOR_SOAK_SECONDS", 60, 60, 900)
    records_per_tick = _bounded_int("RONIN_LIVE_SUPERVISOR_SOAK_RECORDS_PER_TICK", 4, 1, 32)
    interval_seconds = _bounded_float(
        "RONIN_LIVE_SUPERVISOR_SOAK_INTERVAL_SECONDS", 0.25, 0.05, 5.0
    )
    replication_factor = _bounded_int(
        "RONIN_LIVE_STREAMING_REPLICATION_FACTOR", 1, 1, 3
    )
    _create_topic(bootstrap, topic, replication_factor)

    producer = Producer(
        {
            "bootstrap.servers": bootstrap,
            "message.max.bytes": 2 * 1024 * 1024,
        }
    )
    stop_requested = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    print(json.dumps({"status": "ready", "topic": topic, "partitions": 2}), flush=True)
    started = time.monotonic()
    deadline = started + duration_seconds
    produced = 0
    try:
        while not stop_requested and time.monotonic() < deadline:
            for _ in range(records_per_tick):
                partition = produced % 2
                producer.produce(
                    topic,
                    partition=partition,
                    key=f"ronin-supervisor-soak-{produced}",
                    value=json.dumps(
                        {"event": f"supervisor-soak-{produced}", "sequence": produced},
                        separators=(",", ":"),
                    ),
                )
                produced += 1
            producer.poll(0)
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(interval_seconds, remaining))
        if producer.flush(30) != 0:
            raise RuntimeError("Kafka did not acknowledge all supervisor soak records")
    except Exception as exc:
        print(json.dumps({"status": "failed", "produced": produced, "error": str(exc)}), flush=True)
        return 1

    elapsed = round(time.monotonic() - started, 2)
    print(
        json.dumps(
            {
                "status": "completed",
                "topic": topic,
                "produced": produced,
                "duration_seconds": elapsed,
            }
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
