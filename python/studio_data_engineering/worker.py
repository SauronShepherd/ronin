"""Execution handler contract for data-engineering pipeline jobs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from .previews import PreviewError, preview_pipeline
from .spark_connect import SparkConnectProvider, SparkConnectUnavailable


class PipelineExecutionError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class PipelineWorkerResult:
    state: str
    runtime: str
    output: Mapping[str, object]
    evidence: Mapping[str, object]


def execute_pipeline_job(payload: Mapping[str, object]) -> PipelineWorkerResult:
    """Execute the bounded local runtime; remote runtimes are explicit adapters."""
    runtime = payload.get("runtime")
    pipeline = payload.get("pipeline")
    if not isinstance(runtime, str) or not runtime.strip():
        raise PipelineExecutionError("DE-EXEC-001", "runtime is required")
    if not isinstance(pipeline, dict):
        raise PipelineExecutionError("DE-EXEC-002", "pipeline must be an object")
    if runtime == "spark-connect":
        endpoint = payload.get("endpoint")
        sql = payload.get("sql")
        if not isinstance(endpoint, str) or not endpoint.strip():
            raise PipelineExecutionError("DE-EXEC-006", "Spark Connect endpoint is required")
        if not isinstance(sql, str) or not sql.strip():
            raise PipelineExecutionError(
                "DE-EXEC-007", "compiled SQL is required for Spark Connect"
            )
        try:
            spark_result = SparkConnectProvider(endpoint).execute_sql(
                sql, limit=int(cast(int | str, payload.get("row_limit", 100)))
            )
        except (SparkConnectUnavailable, ValueError) as exc:
            raise PipelineExecutionError("DE-EXEC-008", str(exc), retryable=True) from exc
        return PipelineWorkerResult(
            "succeeded",
            runtime,
            {"rows": [dict(row) for row in spark_result.rows], "row_count": spark_result.row_count},
            {"kind": "data-engineering.spark-connect", "endpoint": spark_result.endpoint},
        )
    if runtime != "local-preview":
        raise PipelineExecutionError(
            "DE-EXEC-003",
            f"runtime adapter is not installed: {runtime}",
        )
    fixtures = payload.get("fixtures", {})
    if not isinstance(fixtures, dict):
        raise PipelineExecutionError("DE-EXEC-004", "fixtures must be an object")
    try:
        result = preview_pipeline(
            pipeline,
            fixtures=fixtures,
            row_limit=int(cast(int | str, payload.get("row_limit", 100))),
        )
    except (PreviewError, ValueError, TypeError) as exc:
        raise PipelineExecutionError("DE-EXEC-005", str(exc)) from exc
    output = {
        "rows_by_node": {key: list(rows) for key, rows in result.rows_by_node.items()},
        "metrics": dict(result.metrics),
    }
    evidence = {
        "kind": "data-engineering.preview",
        "runtime": result.runtime,
        "payload_digest": _digest(payload),
        "row_count": sum(item["output_rows"] for item in result.metrics.values()),
    }
    return PipelineWorkerResult("succeeded", runtime, output, evidence)


def _digest(payload: Mapping[str, object]) -> str:
    import hashlib

    return hashlib.sha256(
        json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


__all__ = ("PipelineExecutionError", "PipelineWorkerResult", "execute_pipeline_job")
