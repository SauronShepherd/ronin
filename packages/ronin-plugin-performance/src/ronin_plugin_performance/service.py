"""Application service exposed by the Performance Studio job contribution."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .analyzer import analyze_run
from .correlation import compare_runs, correlate
from .policy import PerformancePolicy


def analyze_performance(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Produce one complete, UI-ready report from current and optional baseline runs."""
    current = payload.get("run", payload)
    if not isinstance(current, Mapping):
        raise ValueError("performance payload requires a run object")
    result = analyze_run(current, PerformancePolicy.from_mapping(payload.get("policy")))
    result["correlation"] = correlate(current)
    baseline = payload.get("baseline")
    result["regression"] = (
        compare_runs(current, baseline) if isinstance(baseline, Mapping) else None
    )
    result["best_practices"] = [
        {
            "id": "partition-sizing",
            "title": "Size partitions from observed task and shuffle metrics",
            "when": "always",
            "source": "stage metrics",
        },
        {
            "id": "early-pruning",
            "title": "Filter and project before wide transformations",
            "when": "shuffle-pressure",
            "source": "shuffle metrics",
        },
        {
            "id": "file-compaction",
            "title": "Compact small files and avoid over-partitioned writes",
            "when": "small-files",
            "source": "asset metrics",
        },
        {
            "id": "runtime-overhead",
            "title": "Keep instrumentation bounded and inspect dropped snapshots",
            "when": "runtime telemetry",
            "source": "MadMamba/MadLava metadata",
        },
    ]
    return result


def analyze_http(*, body: object = None, **_: object) -> dict[str, Any]:
    """Adapt Ronin's route invocation envelope to the application service."""
    if not isinstance(body, Mapping):
        raise ValueError("performance analysis request body must be an object")
    return analyze_performance(body)
