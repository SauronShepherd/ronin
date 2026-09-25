from __future__ import annotations

import json
import time

import pytest

from studio_execution import SchedulerSqlResult, execute_scheduler_sql
from studio_orchestrator import Instant, Job, JobId, JobState
from studio_sql import SqlColumn, SqlQueryResult, SqlTimeoutError, SqlValidationError


class FakeEngine:
    def __init__(self, *, delay: float = 0) -> None:
        self.delay = delay
        self.calls: list[tuple[str, tuple[object, ...], int]] = []

    def execute(self, sql: str, parameters: tuple[object, ...], *, max_rows: int) -> SqlQueryResult:
        self.calls.append((sql, parameters, max_rows))
        if self.delay:
            time.sleep(self.delay)
        return SqlQueryResult((SqlColumn("answer", "INTEGER"),), ((1,),))


def _job(target: str = "sql.query", payload: object | None = None) -> Job:
    now = Instant("2026-09-24T00:00:00.000000Z")
    return Job(
        id=JobId("job-1"),
        project_id="project-1",
        idempotency_key="key-1",
        request_digest="a" * 64,
        state=JobState.QUEUED,
        created_at=now,
        updated_at=now,
        target=target,
        parameters_json=json.dumps(
            payload if payload is not None else {"query": "SELECT ?", "parameters": {"value": 1}}
        ),
    )


def test_scheduler_sql_executes_and_returns_content_digest() -> None:
    engine = FakeEngine()
    result = execute_scheduler_sql(_job(), engine, max_rows=25)
    assert isinstance(result, SchedulerSqlResult)
    assert len(result.evidence_digest) == 64
    assert engine.calls == [("SELECT ?", (1,), 25)]


def test_scheduler_sql_rejects_wrong_target() -> None:
    with pytest.raises(SqlValidationError, match="target sql.query"):
        execute_scheduler_sql(_job("notebook.run"), FakeEngine())


def test_scheduler_sql_timeout_is_fail_closed() -> None:
    with pytest.raises(SqlTimeoutError, match="exceeded"):
        execute_scheduler_sql(_job(), FakeEngine(delay=1.1), timeout_seconds=1)
