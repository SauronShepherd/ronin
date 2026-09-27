"""Bounded adapters for the evidence formats emitted by MadMamba/MadLava/Spark."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_spark_events(
    events: Iterable[Mapping[str, Any]], run_id: str | None = None
) -> dict[str, Any]:
    """Normalize Spark event-log JSON objects without requiring PySpark."""
    stages: dict[str, dict[str, Any]] = {}
    for event in events:
        name = event.get("Event", event.get("event", ""))
        if name not in {"SparkListenerStageCompleted", "stage.completed"}:
            continue
        info = event.get("Stage Info", event.get("stage_info", event)) or {}
        sid = str(info.get("Stage ID", info.get("stage_id", event.get("stageId", "unknown"))))
        raw_metrics = info.get("Accumulables", info.get("task_metrics", {})) or {}
        if isinstance(raw_metrics, list):
            metrics = {}
            for item in raw_metrics:
                if isinstance(item, Mapping):
                    name = item.get("Name", item.get("name"))
                    value = item.get("Value", item.get("value"))
                    if name is not None:
                        metrics[str(name)] = value
        else:
            metrics = raw_metrics if isinstance(raw_metrics, Mapping) else {}
        stage = stages.setdefault(
            sid,
            {
                "id": sid,
                "duration_ms": 0,
                "tasks": [],
                "shuffle_read_bytes": 0,
                "shuffle_write_bytes": 0,
                "spill_memory_bytes": 0,
                "spill_disk_bytes": 0,
            },
        )
        stage["duration_ms"] = (
            _num(info.get("completionTime", 0)) - _num(info.get("submissionTime", 0))
            if info.get("completionTime") and info.get("submissionTime")
            else _num(event.get("duration_ms", stage["duration_ms"]))
        )
        for key, target in (
            ("Remote Bytes Read", "shuffle_read_bytes"),
            ("Remote Bytes Read (Fetched)", "shuffle_read_bytes"),
            ("Shuffle Read Bytes", "shuffle_read_bytes"),
            ("Shuffle Write Bytes", "shuffle_write_bytes"),
            ("Memory Bytes Spilled", "spill_memory_bytes"),
            ("Disk Bytes Spilled", "spill_disk_bytes"),
        ):
            if key in metrics:
                stage[target] += _num(metrics[key])
        if event.get("task_metrics"):
            stage["tasks"].extend(
                event["task_metrics"] if isinstance(event["task_metrics"], list) else []
            )
    return {
        "schema": "ronin.performance-run/v1",
        "run_id": run_id,
        "source": "spark-event-log",
        "stages": list(stages.values()),
        "assets": [],
    }


def normalize_madmamba_records(
    records: Iterable[Mapping[str, Any]], run_id: str | None = None
) -> dict[str, Any]:
    """Normalize validated MadMamba bundle records, preserving only metrics."""
    stages: list[dict[str, Any]] = []
    for record in records:
        payload = record.get("payload", record)
        if not isinstance(payload, Mapping):
            continue
        if str(record.get("recordType", "")).startswith(("runtime", "monitor")):
            duration = _num(payload.get("duration_ms", payload.get("durationNanos", 0) / 1_000_000))
            stages.append(
                {
                    "id": record.get("recordType", "runtime"),
                    "duration_ms": duration,
                    "tasks": [],
                    "shuffle_read_bytes": 0,
                    "shuffle_write_bytes": 0,
                    "spill_memory_bytes": 0,
                    "spill_disk_bytes": 0,
                }
            )
    return {
        "schema": "ronin.performance-run/v1",
        "run_id": run_id,
        "source": "madmamba-bundle",
        "stages": stages,
        "assets": [],
    }


def normalize_madlava_snapshots(
    lines: Iterable[str | Mapping[str, Any]], run_id: str | None = None
) -> dict[str, Any]:
    """Turn MadLava JSONL snapshots into runtime stages and method assets."""
    stages: list[dict[str, Any]] = []
    for line in lines:
        value = json.loads(line) if isinstance(line, str) else line
        if not isinstance(value, Mapping):
            continue
        snapshot = value.get("snapshot", value)
        features = value.get("features", {})
        methods = features.get("methodProfiling", {}) if isinstance(features, Mapping) else {}
        duration = _num(snapshot.get("durationNanos", 0)) / 1_000_000
        stages.append(
            {
                "id": f"madlava-{snapshot.get('sequence', len(stages) + 1)}",
                "duration_ms": duration,
                "tasks": [],
                "shuffle_read_bytes": 0,
                "shuffle_write_bytes": 0,
                "spill_memory_bytes": 0,
                "spill_disk_bytes": 0,
                "method_count": len(methods) if isinstance(methods, Mapping) else 0,
            }
        )
    return {
        "schema": "ronin.performance-run/v1",
        "run_id": run_id,
        "source": "madlava-jsonl",
        "stages": stages,
        "assets": [],
    }
