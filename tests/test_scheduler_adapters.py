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
from studio_storage import LocalArtifactStore


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
    with pytest.raises(UnsupportedSchedulerWorkload, match="ml.run requires"):
        execute_scheduler_job(_job("ml.run"))


def test_scheduler_dispatch_routes_genai_run_through_injected_runner() -> None:
    seen: dict[str, object] = {}

    class Runner:
        def run(self, payload: dict[str, object]) -> dict[str, object]:
            seen.update(payload)
            return {"provider_id": payload["provider_id"], "status": "completed"}

    result = execute_scheduler_job(
        _job(
            "genai.run",
            {
                "provider_id": "openai",
                "model_id": "gpt-5",
                "prompt_ref": "artifact://sha256/" + "a" * 64,
            },
        ),
        genai_runner=Runner(),
    )
    assert result.family == "genai"
    assert seen["model_id"] == "gpt-5"
    assert result.evidence_payload()["genai"]["status"] == "completed"


def test_scheduler_dispatch_routes_graph_query() -> None:
    object_ref = SimpleNamespace(object_type="Order", key=(("id", 1),))
    graph_object = SimpleNamespace(ref=object_ref, properties=(("total", 5),))

    def query(_graph_id: str, _query: str, *, max_limit: int) -> SimpleNamespace:
        del max_limit
        return SimpleNamespace(objects=(graph_object,))

    adapter = SimpleNamespace(query=query)
    result = execute_scheduler_job(
        _job(
            "graph.query",
            {"graph_id": "orders", "query": "SELECT o FROM Order o", "limit": 10},
        ),
        graph_adapter=adapter,
    )
    assert result.family == "graph"
    assert result.evidence_payload()["objects"][0]["object_type"] == "Order"


def test_scheduler_dispatch_routes_quality_gate_through_rows_artifact(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)
    rows_ref = store.put_bytes(role="quality-rows", data=b'[{"id": 1}]').storage_ref
    seen: dict[str, object] = {}

    class Quality:
        def run(self, workspace_id, payload, *, now):
            seen.update({"workspace": workspace_id, "payload": payload, "now": now})
            return {"run": {"status": "passed"}, "gate_passed": True}

    result = execute_scheduler_job(
        _job(
            "quality.gate",
            {
                "asset_id": "orders",
                "version": "v1",
                "contract_digest": "a" * 64,
                "rows_ref": rows_ref,
            },
        ),
        quality_adapter=Quality(),
        artifact_store=store,
        workspace_id="workspace-1",
        run_id="run-1",
    )
    assert result.family == "quality"
    assert seen["payload"]["rows"] == [{"id": 1}]
