"""Engine-neutral performance analysis over a bounded normalized run contract."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .policy import PerformancePolicy

SCHEMA = "ronin.performance-run/v1"


def _issue(
    code: str, severity: str, title: str, evidence: dict[str, Any], recommendation: str
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "title": title,
        "evidence": evidence,
        "recommendation": recommendation,
    }


def analyze_run(run: Mapping[str, Any], policy: PerformancePolicy | None = None) -> dict[str, Any]:
    """Return deterministic findings, score and chart-ready series.

    Inputs may come from Spark event logs, MadMamba bundles, or MadLava JSONL
    after normalization. Missing metrics are never guessed; findings state the
    evidence actually available.
    """
    policy = policy or PerformancePolicy()
    stages = list(run.get("stages", []))
    assets = list(run.get("assets", []))
    issues: list[dict[str, Any]] = []
    for stage in stages:
        sid = stage.get("id", "unknown")
        duration = float(stage.get("duration_ms", 0) or 0)
        tasks = list(stage.get("tasks", []))
        durations = [
            float(t.get("duration_ms", 0) or 0) for t in tasks if t.get("duration_ms") is not None
        ]
        shuffle_write = float(stage.get("shuffle_write_bytes", 0) or 0)
        shuffle_read = float(stage.get("shuffle_read_bytes", 0) or 0)
        spill_disk = float(stage.get("spill_disk_bytes", 0) or 0)
        spill_memory = float(stage.get("spill_memory_bytes", 0) or 0)
        gc_ms = float(stage.get("gc_time_ms", 0) or 0)
        task_count = len(tasks) or int(stage.get("task_count", 0) or 0)
        if durations and max(durations) >= max(
            policy.min_skew_task_ms, policy.skew_ratio * (sum(durations) / len(durations))
        ):
            issues.append(
                _issue(
                    "task-skew",
                    "high",
                    "Task duration skew",
                    {
                        "stage_id": sid,
                        "max_ms": max(durations),
                        "mean_ms": round(sum(durations) / len(durations), 2),
                    },
                    "Inspect hot keys; use AQE skew handling, salting, or rebalance partitions.",
                )
            )
        if spill_disk > 0 or spill_memory > 0:
            issues.append(
                _issue(
                    "spill",
                    "high" if spill_disk else "medium",
                    "Shuffle spill detected",
                    {
                        "stage_id": sid,
                        "spill_disk_bytes": spill_disk,
                        "spill_memory_bytes": spill_memory,
                    },
                    "Reduce partition pressure, review executor memory, and tune partition sizing before raising cluster capacity.",  # noqa: E501
                )
            )
        if duration > 0 and gc_ms / duration >= policy.gc_ratio:
            issues.append(
                _issue(
                    "gc-pressure",
                    "medium",
                    "Garbage collection consumes a large share of stage time",
                    {
                        "stage_id": sid,
                        "gc_time_ms": gc_ms,
                        "duration_ms": duration,
                        "gc_ratio": round(gc_ms / duration, 4),
                    },
                    "Review object churn, serialization and executor heap sizing; prefer bounded aggregation and efficient encoders.",  # noqa: E501
                )
            )  # noqa: E501
        if task_count == 1 and duration >= policy.min_skew_task_ms:
            issues.append(
                _issue(
                    "low-parallelism",
                    "medium",
                    "Stage has only one long-running task",
                    {"stage_id": sid, "task_count": task_count, "duration_ms": duration},
                    "Check partitioning and input splits; increase parallelism only when the data volume supports it.",  # noqa: E501
                )
            )  # noqa: E501
        if (
            shuffle_write + shuffle_read > 0
            and duration > 0
            and (shuffle_write + shuffle_read) / duration * 1000 > policy.shuffle_bytes_per_second
        ):
            issues.append(
                _issue(
                    "shuffle-pressure",
                    "medium",
                    "High shuffle throughput",
                    {
                        "stage_id": sid,
                        "shuffle_bytes": shuffle_write + shuffle_read,
                        "bytes_per_ms": round((shuffle_write + shuffle_read) / duration, 2),
                    },
                    "Prefer early filtering/projection, broadcast safe small dimensions, and verify join keys and partition count.",  # noqa: E501
                )
            )
    for asset in assets:
        count = int(asset.get("file_count", 0) or 0)
        total = int(asset.get("bytes", 0) or 0)
        avg = total / count if count else 0
        if count >= policy.small_file_count and avg and avg < policy.small_file_average_bytes:
            issues.append(
                _issue(
                    "small-files",
                    "medium",
                    "Small-file pressure",
                    {
                        "asset": asset.get("id", asset.get("path", "unknown")),
                        "file_count": count,
                        "average_file_bytes": round(avg),
                    },
                    "Compact files, target appropriately sized objects, and avoid over-partitioned writes.",  # noqa: E501
                )
            )
    score = max(0, 100 - sum({"high": 25, "medium": 12, "low": 5}[i["severity"]] for i in issues))
    return {
        "schema": SCHEMA,
        "run_id": run.get("run_id"),
        "policy": policy.to_mapping(),
        "score": score,
        "issues": issues,
        "series": {
            "stages": [
                {
                    "id": s.get("id"),
                    "duration_ms": s.get("duration_ms", 0),
                    "shuffle_bytes": (s.get("shuffle_read_bytes", 0) or 0)
                    + (s.get("shuffle_write_bytes", 0) or 0),
                    "spill_bytes": (s.get("spill_disk_bytes", 0) or 0)
                    + (s.get("spill_memory_bytes", 0) or 0),
                }
                for s in stages
            ]
        },
    }
