"""Correlation and regression primitives for Performance Studio."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def correlate(run: Mapping[str, Any]) -> dict[str, Any]:
    """Attach asset/runtime context to each stage without inventing lineage."""
    assets = {
        str(a.get("id", a.get("path", ""))): a
        for a in run.get("assets", [])
        if isinstance(a, Mapping)
    }
    runtimes = {
        str(r.get("id", r.get("runtime", ""))): r
        for r in run.get("runtimes", [])
        if isinstance(r, Mapping)
    }
    rows = []
    for stage in run.get("stages", []):
        if not isinstance(stage, Mapping):
            continue
        asset_ids = [str(x) for x in stage.get("asset_ids", [])]
        runtime_id = stage.get("runtime_id")
        rows.append(
            {
                "stage_id": stage.get("id"),
                "asset_ids": asset_ids,
                "assets": [assets[x] for x in asset_ids if x in assets],
                "runtime_id": runtime_id,
                "runtime": runtimes.get(str(runtime_id)) if runtime_id is not None else None,
                "method_ids": list(stage.get("method_ids", [])),
            }
        )
    return {"schema": "ronin.performance-correlation/v1", "run_id": run.get("run_id"), "rows": rows}


def compare_runs(
    current: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    duration_regression: float = 0.20,
    shuffle_regression: float = 0.25,
) -> dict[str, Any]:
    """Compare stage aggregates and emit explainable regressions."""
    old = {str(s.get("id")): s for s in baseline.get("stages", []) if isinstance(s, Mapping)}
    changes = []
    for stage in current.get("stages", []):
        if not isinstance(stage, Mapping) or str(stage.get("id")) not in old:
            continue
        previous = old[str(stage.get("id"))]
        duration_old = float(previous.get("duration_ms", 0) or 0)
        duration_new = float(stage.get("duration_ms", 0) or 0)
        shuffle_old = float(previous.get("shuffle_read_bytes", 0) or 0) + float(
            previous.get("shuffle_write_bytes", 0) or 0
        )
        shuffle_new = float(stage.get("shuffle_read_bytes", 0) or 0) + float(
            stage.get("shuffle_write_bytes", 0) or 0
        )
        duration_delta = round(duration_new / duration_old - 1, 6) if duration_old else None
        shuffle_delta = round(shuffle_new / shuffle_old - 1, 6) if shuffle_old else None
        if (duration_delta is not None and duration_delta >= duration_regression) or (
            shuffle_delta is not None and shuffle_delta >= shuffle_regression
        ):
            changes.append(
                {
                    "stage_id": stage.get("id"),
                    "duration_delta": duration_delta,
                    "shuffle_delta": shuffle_delta,
                    "baseline_duration_ms": duration_old,
                    "current_duration_ms": duration_new,
                }
            )
    return {
        "schema": "ronin.performance-regression/v1",
        "run_id": current.get("run_id"),
        "baseline_run_id": baseline.get("run_id"),
        "regressions": changes,
        "has_regressions": bool(changes),
    }
