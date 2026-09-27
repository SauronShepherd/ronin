"""SQL scheduler adapter over the provider-neutral SQL engine port."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import cast

from studio_orchestrator import Job
from studio_sql import SqlEngine, SqlQueryResult, SqlTimeoutError, SqlValidationError


@dataclass(frozen=True, slots=True)
class SchedulerSqlResult:
    result: SqlQueryResult
    evidence_digest: str


def _canonical_result(result: SqlQueryResult) -> bytes:
    return json.dumps(
        {
            "columns": [
                {"name": column.name, "type": column.type_name} for column in result.columns
            ],
            "rows": result.rows,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def execute_scheduler_sql(
    job: Job,
    engine: SqlEngine,
    *,
    max_rows: int = 10_000,
    timeout_seconds: int | None = None,
) -> SchedulerSqlResult:
    """Execute one scheduler ``sql.query`` Job with bounded result semantics."""

    if job.target != "sql.query":
        raise SqlValidationError("scheduler SQL adapter requires target sql.query")
    try:
        payload = json.loads(job.parameters_json)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SqlValidationError("scheduler SQL parameters must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise SqlValidationError("scheduler SQL parameters must be a JSON object")
    query = payload.get("query")
    parameters = payload.get("parameters", {})
    if not isinstance(query, str) or not query.strip():
        raise SqlValidationError("scheduler SQL query must be non-empty")
    if not isinstance(parameters, dict) or not all(isinstance(key, str) for key in parameters):
        raise SqlValidationError("scheduler SQL parameters must be a JSON object")
    if not isinstance(max_rows, int) or isinstance(max_rows, bool) or not 1 <= max_rows <= 100_000:
        raise SqlValidationError("max_rows must be between 1 and 100000")
    if timeout_seconds is not None and (
        not isinstance(timeout_seconds, int)
        or isinstance(timeout_seconds, bool)
        or not 1 <= timeout_seconds <= 7 * 24 * 60 * 60
    ):
        raise SqlValidationError("timeout_seconds must be between 1 and 604800")

    def run() -> SqlQueryResult:
        ordered = tuple(parameters[key] for key in sorted(parameters))
        return engine.execute(query.strip(), ordered, max_rows=max_rows)

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="ronin-scheduler-sql") as pool:
        future = pool.submit(run)
        try:
            result = future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise SqlTimeoutError("scheduler SQL query exceeded its timeout") from exc
    digest = hashlib.sha256(_canonical_result(result)).hexdigest()
    return SchedulerSqlResult(result=cast(SqlQueryResult, result), evidence_digest=digest)


__all__ = ("SchedulerSqlResult", "execute_scheduler_sql")
