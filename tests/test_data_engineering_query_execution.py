from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

import pytest
from studio_data_engineering import (
    QueryEngineRuntimeProvider,
    SqliteQueryEvidenceReferenceStore,
    execute_query,
)
from studio_data_engineering.result_paging import page_query_result
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


class _ThreeRowTransport(_Transport):
    def __init__(self) -> None:
        super().__init__([QueryStatus("running"), QueryStatus("succeeded")])
        self.pages = iter(
            (QueryResultPage(("id",), ((1,), (2,))), QueryResultPage(("id",), ((3,),)))
        )

    def poll(self, _handle, _next_uri):
        status = self.states.pop(0)
        return status, next(self.pages), "next-2" if status.state == "running" else None


class _FailedAfterRowsTransport(_Transport):
    def __init__(self) -> None:
        super().__init__([QueryStatus("failed", "provider query failed")])

    def poll(self, _handle, _next_uri):
        return (
            QueryStatus("failed", "provider query failed"),
            QueryResultPage(("id",), ((1,),)),
            None,
        )


class _MismatchedTransport(_Transport):
    def submit(self, _request: QueryRequest) -> tuple[QueryHandle, str]:
        return QueryHandle("ronin-q-1", "other-provider", "other-q-1"), "next-1"


class _OversizedRunningTransport(_Transport):
    def __init__(self) -> None:
        super().__init__([QueryStatus("running")])
        self.cancelled = False

    def poll(self, _handle, _next_uri):
        return (
            QueryStatus("running"),
            QueryResultPage(("value",), (("x" * 256,),)),
            "next-2",
        )

    def cancel(self, _handle):
        self.cancelled = True
        return type("Cancellation", (), {"cancelled": True})()


def _provider() -> QueryEngineRuntimeProvider:
    return QueryEngineRuntimeProvider(
        DiscoveredEngine(
            EngineHandshake(
                "provider",
                "1",
                EngineCapabilities((("cancel", True), ("parameter_binding", True))),
                True,
            ),
            ("duckdb",),
            "ready",
        ),
        QueryExecutionPolicy((("local", ("duckdb",)),), required_capability="cancel"),
    )


def test_execute_query_persists_final_attempt_evidence(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    request = QueryRequest("SELECT ?", "local", parameters=(11,))
    result = execute_query(
        _provider(),
        _Transport([QueryStatus("running"), QueryStatus("succeeded")]),
        store,
        request,
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
    assert (
        payload["query_evidence"]["request_digest"]
        == hashlib.sha256(request.canonical_json().encode("utf-8")).hexdigest()
    )
    assert '"value":"11"' not in json.dumps(payload["query_evidence"])


def test_execute_query_rejects_transport_provider_mismatch(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")

    with pytest.raises(RuntimeError, match="does not match authorized runtime provider"):
        execute_query(
            _provider(),
            _MismatchedTransport([]),
            store,
            QueryRequest("SELECT 1", "local"),
            engine="duckdb",
            project_id="project-1",
            run_id="run-1",
            attempt_id="attempt-1",
        )


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


def test_execute_query_does_not_return_or_persist_partial_rows_on_failure(
    tmp_path: Path,
) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    result = execute_query(
        _provider(),
        _FailedAfterRowsTransport(),
        store,
        QueryRequest("SELECT id", "local"),
        engine="duckdb",
        project_id="project-1",
        run_id="run-failed",
        attempt_id="attempt-failed",
    )

    evidence = json.loads(store.get_bytes(result.evidence_artifact))
    assert result.status.state == "failed"
    assert result.page is None
    assert result.row_count == 0
    assert result.next_cursor is None
    assert evidence["output"] == {"columns": [], "row_count": 0, "rows": []}


def test_execute_query_persists_full_result_and_returns_a_durable_page_cursor(
    tmp_path: Path,
) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    result = execute_query(
        _provider(),
        _ThreeRowTransport(),
        store,
        QueryRequest("SELECT id", "local", max_rows=3),
        engine="duckdb",
        project_id="project-1",
        run_id="run-1",
        attempt_id="attempt-1",
        page_size=2,
    )

    assert result.page is not None
    assert result.page.rows == ((1,), (2,))
    assert result.row_count == 3
    assert isinstance(result.next_cursor, str)
    payload = json.loads(store.get_bytes(result.evidence_artifact))
    assert payload["output"] == {
        "row_count": 3,
        "columns": ["id"],
        "rows": [[1], [2], [3]],
    }
    second = page_query_result(
        columns=payload["output"]["columns"],
        rows=payload["output"]["rows"],
        digest=result.evidence_artifact.digest,
        cursor=result.next_cursor,
        page_size=2,
    )
    assert second["rows"] == [[3]]
    assert second["next_cursor"] is None


def test_execute_query_fails_instead_of_silently_truncating_rows(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    result = execute_query(
        _provider(),
        _PagedTransport(),
        store,
        QueryRequest("SELECT id", "local", max_rows=1),
        engine="duckdb",
        project_id="project-1",
        run_id="run-1",
        attempt_id="attempt-1",
    )

    assert result.status.state == "failed"
    assert result.status.message == "query result exceeds the configured row limit"
    assert result.page is None


def test_execute_query_cancels_when_result_byte_budget_is_exceeded(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    transport = _OversizedRunningTransport()
    result = execute_query(
        _provider(),
        transport,
        store,
        QueryRequest("SELECT value", "local", max_result_bytes=64),
        engine="duckdb",
        project_id="project-1",
        run_id="run-1",
        attempt_id="attempt-1",
    )

    assert transport.cancelled
    assert result.status.state == "failed"
    assert result.status.message == "query result exceeds the configured byte limit"
    assert result.page is None


def test_execute_query_accepts_result_at_exact_serialized_byte_budget(tmp_path: Path) -> None:
    serialized_result = json.dumps(
        {"columns": ["id"], "rows": [[1]], "row_count": 1},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    store = LocalArtifactStore(tmp_path / "artifacts")
    result = execute_query(
        _provider(),
        _Transport([QueryStatus("succeeded")]),
        store,
        QueryRequest("SELECT 1", "local", max_result_bytes=len(serialized_result)),
        engine="duckdb",
        project_id="project-1",
        run_id="run-1",
        attempt_id="attempt-1",
    )

    assert result.status.state == "succeeded"
    assert result.page is not None
    assert result.page.rows == ((1,),)


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
    assert payload["query_evidence"]["provider_version"] == "1"
    assert payload["query_evidence"]["cluster_id"] is None
    assert payload["query_evidence"]["routing_trace"] == {"selected_engine": "duckdb"}


def test_execute_query_holds_writer_lease_through_durable_reference_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = LocalArtifactStore(tmp_path / "artifacts")
    references = SqliteQueryEvidenceReferenceStore(tmp_path / "ronin.db")
    events: list[str] = []

    class Barrier:
        @contextmanager
        def writer(self):
            events.append("lock")
            try:
                yield
            finally:
                events.append("unlock")

    original_put_bytes = artifacts.put_bytes

    def put_bytes(**kwargs):
        events.append("artifact")
        return original_put_bytes(**kwargs)

    monkeypatch.setattr(artifacts, "put_bytes", put_bytes)
    original_record = references.record

    def record(**kwargs):
        events.append("reference")
        original_record(**kwargs)

    monkeypatch.setattr(references, "record", record)
    result = execute_query(
        _provider(),
        _Transport([QueryStatus("succeeded")]),
        artifacts,
        QueryRequest("SELECT 1", "local"),
        engine="duckdb",
        project_id="project-1",
        run_id="run-1",
        attempt_id="attempt-1",
        evidence_reference_store=references,
        artifact_reference_barrier=Barrier(),
    )

    assert events == ["lock", "artifact", "reference", "unlock"]
    assert references.list_evidence_references()[0]["digest"] == result.evidence_artifact.digest
