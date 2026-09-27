"""Bounded query-engine execution orchestration for Data Engineering workers."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from studio_query_engine import (
    CancellationResult,
    QueryEvidence,
    QueryHandle,
    QueryRequest,
    QueryResultPage,
    QueryStatus,
)
from studio_storage import ArtifactRef

from .evidence import EvidenceStore, persist_query_engine_evidence
from .runtimes import QueryEngineRuntimeProvider


class QueryTransport(Protocol):
    def submit(self, request: QueryRequest) -> tuple[QueryHandle, str]: ...

    def poll(
        self, handle: QueryHandle, next_uri: str
    ) -> tuple[QueryStatus, QueryResultPage | None, str | None]: ...

    def cancel(self, handle: QueryHandle) -> CancellationResult: ...


@dataclass(frozen=True, slots=True)
class QueryExecutionResult:
    status: QueryStatus
    page: QueryResultPage | None
    evidence_artifact: ArtifactRef
    selected_engine: str


def execute_query(
    provider: QueryEngineRuntimeProvider,
    transport: QueryTransport,
    store: EvidenceStore,
    request: QueryRequest,
    *,
    engine: str,
    project_id: str,
    run_id: str,
    attempt_id: str,
    max_polls: int = 100,
    clock: Callable[[], float] = time.monotonic,
) -> QueryExecutionResult:
    """Run one bounded query lifecycle and persist its final evidence."""

    if max_polls < 1:
        raise ValueError("max_polls must be positive")
    started = clock()
    selected = provider.authorize(request, engine=engine)
    request_digest = hashlib.sha256(request.canonical_json().encode("utf-8")).hexdigest()
    authorized = clock()
    handle, next_uri = transport.submit(request)
    submitted = clock()
    status = QueryStatus("queued", provider_query_id=handle.provider_query_id)
    columns: tuple[str, ...] | None = None
    rows: list[tuple[object, ...]] = []
    for _ in range(max_polls):
        status, page, following_uri = transport.poll(handle, next_uri)
        if page is not None:
            if columns is None:
                columns = page.columns
            elif columns != page.columns:
                raise RuntimeError("query transport returned inconsistent result columns")
            remaining = request.max_rows - len(rows)
            if remaining > 0:
                rows.extend(page.rows[:remaining])
        if status.state in {"succeeded", "failed", "cancelled"}:
            break
        if following_uri is None:
            raise RuntimeError("query transport returned a non-terminal status without next URI")
        next_uri = following_uri
    else:
        cancellation = transport.cancel(handle)
        status = QueryStatus(
            "cancelled" if cancellation.cancelled else "failed",
            "query exceeded polling limit",
            provider_query_id=handle.provider_query_id,
        )
        columns = None
        rows = []

    result_page = QueryResultPage(columns or (), tuple(rows)) if columns is not None else None
    finished = clock()

    evidence = QueryEvidence(
        request_digest,
        handle.provider_id,
        handle.provider_query_id,
        selected,
        timings_ms=(
            ("authorization", max(0, int((authorized - started) * 1000))),
            ("submission", max(0, int((submitted - authorized) * 1000))),
            ("total", max(0, int((finished - started) * 1000))),
        ),
        cancelled=status.state == "cancelled",
        engine_stats=(("rows_returned", len(rows)),),
    )
    artifact = persist_query_engine_evidence(
        store,
        project_id=project_id,
        run_id=run_id,
        attempt_id=attempt_id,
        query_evidence=evidence,
        status=status,
        output={"row_count": len(rows)},
    )
    return QueryExecutionResult(status, result_page, artifact, selected)


__all__ = ("QueryExecutionResult", "QueryTransport", "execute_query")
