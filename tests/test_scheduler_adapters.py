from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from studio_execution import (
    UnsupportedSchedulerWorkload,
    execute_scheduler_job,
)
from studio_orchestrator import Instant, Job, JobId, JobState
from studio_sql import SqlColumn, SqlQueryResult


class Engine:
    def execute(self, sql: str, parameters: tuple[object, ...], *, max_rows: int) -> SqlQueryResult:
        del max_rows
        assert sql == "SELECT 1"
        assert parameters == ()
        return SqlQueryResult((SqlColumn("value", "INTEGER"),), ((1,),))


def _job(target: str, payload: object | None = None) -> Job:
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
            payload if payload is not None else {"query": "SELECT 1", "parameters": {}}
        ),
    )


def test_scheduler_dispatch_routes_sql_without_notebook_fallback() -> None:
    result = execute_scheduler_job(_job("sql.query"), sql_engine=Engine())
    assert result.family == "sql"
    assert result.sql is not None
    assert result.sql.result.rows == ((1,),)
    assert result.evidence_payload()["evidence_digest"] == result.sql.evidence_digest
    assert result.evidence_payload()["rows"] == [[1]]


def test_scheduler_dispatch_rejects_unqualified_family() -> None:
    with pytest.raises(UnsupportedSchedulerWorkload, match="no qualified"):
        execute_scheduler_job(_job("ml.run"))


def test_scheduler_dispatch_routes_graph_query() -> None:
    object_ref = SimpleNamespace(object_type="Order", key=(("id", 1),))
    graph_object = SimpleNamespace(ref=object_ref, properties=(("total", 5),))
    adapter = SimpleNamespace(
        query=lambda _graph_id, _query, *, _max_limit: SimpleNamespace(objects=(graph_object,))
    )
    result = execute_scheduler_job(
        _job(
            "graph.query",
            {"graph_id": "orders", "query": "SELECT o FROM Order o", "limit": 10},
        ),
        graph_adapter=adapter,
    )
    assert result.family == "graph"
    assert result.evidence_payload()["objects"][0]["object_type"] == "Order"
