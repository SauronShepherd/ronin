from __future__ import annotations

import json
from pathlib import Path

from studio_data_engineering import QueryEngineRuntimeProvider, execute_query
from studio_query_engine import (
    DiscoveredEngine,
    EngineCapabilities,
    EngineHandshake,
    QueryExecutionPolicy,
    QueryHandle,
    QueryRequest,
    QueryResultPage,
    QueryStatus,
)
from studio_storage import LocalArtifactStore


class _Transport:
    def __init__(self, states: list[QueryStatus]) -> None:
        self.states = states
        self.cancelled = False

    def submit(self, _request: QueryRequest) -> tuple[QueryHandle, str]:
        return QueryHandle("ronin-q-1", "provider", "provider-q-1"), "next-1"

    def poll(
        self, _handle: QueryHandle, _next_uri: str
    ) -> tuple[QueryStatus, QueryResultPage | None, str | None]:
        status = self.states.pop(0)
        page = QueryResultPage(("id",), ((1,),)) if status.state == "succeeded" else None
        return status, page, "next-2" if status.state == "running" else None

    def cancel(self, _handle: QueryHandle):
        self.cancelled = True
        return type("Cancellation", (), {"cancelled": True})()


class _PagedTransport(_Transport):
    def __init__(self) -> None:
        super().__init__([QueryStatus("running"), QueryStatus("succeeded")])
        self.pages = iter((QueryResultPage(("id",), ((1,),)), QueryResultPage(("id",), ((2,),))))

    def poll(self, _handle, _next_uri):
        status = self.states.pop(0)
        return status, next(self.pages), "next-2" if status.state == "running" else None


def _provider() -> QueryEngineRuntimeProvider:
    return QueryEngineRuntimeProvider(
        DiscoveredEngine(
            EngineHandshake("provider", "1", EngineCapabilities((("cancel", True),)), True),
            ("duckdb",),
            "ready",
        ),
        QueryExecutionPolicy((("local", ("duckdb",)),), required_capability="cancel"),
    )


def test_execute_query_persists_final_attempt_evidence(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    result = execute_query(
        _provider(),
        _Transport([QueryStatus("running"), QueryStatus("succeeded")]),
        store,
        QueryRequest("SELECT 1", "local"),
        engine="duckdb",
        project_id="project-1",
        run_id="run-1",
        attempt_id="attempt-1",
    )

    payload = json.loads(store.get_bytes(result.evidence_artifact))
    assert result.status.state == "succeeded"
    assert result.page is not None
    assert result.page.rows == ((1,),)
    assert payload["attempt_id"] == "attempt-1"
    assert payload["output"]["row_count"] == 1


def test_execute_query_cancels_when_poll_budget_is_exhausted(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    transport = _Transport([QueryStatus("running")])
    result = execute_query(
        _provider(),
        transport,
        store,
        QueryRequest("SELECT 1", "local"),
        engine="duckdb",
        project_id="project-1",
        run_id="run-1",
        attempt_id="attempt-1",
        max_polls=1,
    )

    assert transport.cancelled
    assert result.status.state == "cancelled"


def test_execute_query_accumulates_bounded_pages(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    result = execute_query(
        _provider(),
        _PagedTransport(),
        store,
        QueryRequest("SELECT id", "local", max_rows=2),
        engine="duckdb",
        project_id="project-1",
        run_id="run-1",
        attempt_id="attempt-1",
    )

    assert result.page is not None
    assert result.page.rows == ((1,), (2,))


def test_execute_query_persists_monotonic_lifecycle_timings(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    ticks = iter((1.0, 1.002, 1.005, 1.021))
    result = execute_query(
        _provider(),
        _Transport([QueryStatus("succeeded")]),
        store,
        QueryRequest("SELECT 1", "local"),
        engine="duckdb",
        project_id="project-1",
        run_id="run-1",
        attempt_id="attempt-1",
        clock=lambda: next(ticks),
    )

    payload = json.loads(store.get_bytes(result.evidence_artifact))
    assert payload["query_evidence"]["timings_ms"] == {
        "authorization": 2,
        "submission": 2,
        "total": 20,
    }
