"""Execution handler contract for data-engineering pipeline jobs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from studio_core import redact_sensitive_text

from .previews import PreviewError, preview_pipeline
from .spark_connect import SparkConnectProvider, SparkConnectUnavailable

_MAX_ROW_LIMIT = 10_000
_MAX_ERROR_MESSAGE_LENGTH = 512


class PipelineExecutionError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        if (
            not isinstance(code, str)
            or not code
            or code != code.strip()
            or "\n" in code
            or "\r" in code
            or len(code) > 128
        ):
            raise ValueError("pipeline execution error code must be bounded single-line text")
        safe_message = redact_sensitive_text(message).replace("\r", " ").replace("\n", " ").strip()
        if not safe_message:
            safe_message = "pipeline execution failed"
        if len(safe_message) > _MAX_ERROR_MESSAGE_LENGTH:
            safe_message = safe_message[: _MAX_ERROR_MESSAGE_LENGTH - 14] + "...[truncated]"
        super().__init__(safe_message)
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
    row_limit = _row_limit(payload.get("row_limit", 100))
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
            spark_result = SparkConnectProvider(endpoint).execute_sql(sql, limit=row_limit)
        except SparkConnectUnavailable as exc:
            raise PipelineExecutionError("DE-EXEC-008", str(exc), retryable=True) from exc
        except ValueError as exc:
            raise PipelineExecutionError("DE-EXEC-008", str(exc)) from exc
        except Exception as exc:
            raise PipelineExecutionError(
                "DE-EXEC-009", "Spark Connect execution failed", retryable=True
            ) from exc
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
            row_limit=row_limit,
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


def _row_limit(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= _MAX_ROW_LIMIT:
        raise PipelineExecutionError(
            "DE-EXEC-010", "row_limit must be an integer between 1 and 10000"
        )
    return value


__all__ = ("PipelineExecutionError", "PipelineWorkerResult", "execute_pipeline_job")
