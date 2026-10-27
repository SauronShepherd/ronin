"""Bounded query-engine execution orchestration for Data Engineering workers."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from contextlib import nullcontext
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
from studio_storage.ports import ArtifactReferenceBarrier

from .evidence import EvidenceStore, persist_query_engine_evidence
from .result_paging import page_query_result
from .runtimes import QueryEngineRuntimeProvider

_LOGGER = logging.getLogger(__name__)


class QueryTransport(Protocol):
    def submit(self, request: QueryRequest) -> tuple[QueryHandle, str]: ...

    def poll(
        self, handle: QueryHandle, next_uri: str
    ) -> tuple[QueryStatus, QueryResultPage | None, str | None]: ...

    def cancel(self, handle: QueryHandle) -> CancellationResult: ...


class QueryEvidenceReferenceStore(Protocol):
    def record(
        self,
        *,
        project_id: str,
        run_id: str,
        attempt_id: str,
        artifact: ArtifactRef,
    ) -> None: ...

    def get_evidence_reference(
        self, *, project_id: str, run_id: str, attempt_id: str
    ) -> dict[str, str] | None: ...


@dataclass(frozen=True, slots=True)
class QueryExecutionResult:
    status: QueryStatus
    page: QueryResultPage | None
    row_count: int
    next_cursor: str | None
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
    evidence_reference_store: QueryEvidenceReferenceStore | None = None,
    artifact_reference_barrier: ArtifactReferenceBarrier | None = None,
    page_size: int = 1_000,
    max_polls: int = 100,
    clock: Callable[[], float] = time.monotonic,
) -> QueryExecutionResult:
    """Run one bounded query lifecycle and persist its final evidence."""

    if max_polls < 1:
        raise ValueError("max_polls must be positive")
    if (
        isinstance(page_size, bool)
        or not isinstance(page_size, int)
        or not 1 <= page_size <= 10_000
    ):
        raise ValueError("page_size must be between 1 and 10000")
    started = clock()
    selected = provider.authorize(request, engine=engine)
    request_digest = hashlib.sha256(request.canonical_json().encode("utf-8")).hexdigest()
    authorized = clock()
    handle, next_uri = transport.submit(request)
    expected_provider = provider.handshake().provider
    if handle.provider_id != expected_provider:
        raise RuntimeError("query transport provider does not match authorized runtime provider")
    submitted = clock()
    status = QueryStatus("queued", provider_query_id=handle.provider_query_id)
    columns: tuple[str, ...] | None = None
    rows: list[tuple[object, ...]] = []
    encoded_rows_bytes = 0
    limit_failure: str | None = None
    for _ in range(max_polls):
        status, page, following_uri = transport.poll(handle, next_uri)
        if page is not None:
            if columns is None:
                columns = page.columns
            elif columns != page.columns:
                raise RuntimeError("query transport returned inconsistent result columns")
            if len(rows) + len(page.rows) > request.max_rows:
                limit_failure = "query result exceeds the configured row limit"
            else:
                columns_json = json.dumps(
                    list(columns), ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")
                empty_result_bytes = len(b'{"columns":' + columns_json + b',"rows":[]') + len(
                    b',"row_count":0}'
                )
                if empty_result_bytes > request.max_result_bytes:
                    limit_failure = "query result exceeds the configured byte limit"
                for row in page.rows:
                    if limit_failure is not None:
                        break
                    try:
                        encoded_row = json.dumps(
                            list(row),
                            ensure_ascii=False,
                            allow_nan=False,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    except (TypeError, ValueError):
                        limit_failure = "query result contains a value that is not JSON-safe"
                        break
                    next_count = len(rows) + 1
                    next_rows_bytes = encoded_rows_bytes + len(encoded_row)
                    if next_count > 1:
                        next_rows_bytes += next_count - 1
                    result_prefix = b'{"columns":' + columns_json + b',"rows":['
                    result_suffix = b'],"row_count":' + str(next_count).encode("ascii") + b"}"
                    if len(result_prefix) + next_rows_bytes + len(result_suffix) > (
                        request.max_result_bytes
                    ):
                        limit_failure = "query result exceeds the configured byte limit"
                        break
                    rows.append(row)
                    encoded_rows_bytes += len(encoded_row)
        if limit_failure is not None:
            if status.state in {"queued", "running"}:
                try:
                    cancellation = transport.cancel(handle)
                    if not cancellation.cancelled:
                        _LOGGER.warning(
                            "query cancellation was not confirmed after a result limit failure"
                        )
                except Exception:
                    _LOGGER.warning(
                        "query cancellation was not confirmed after a result limit failure"
                    )
            status = QueryStatus(
                "failed", limit_failure, provider_query_id=handle.provider_query_id
            )
            columns = None
            rows.clear()
            break
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

    provider_version, cluster_id = provider.evidence_context()
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
        provider_version=provider_version,
        cluster_id=cluster_id,
        routing_trace=(("selected_engine", selected),),
    )
    lease = (
        artifact_reference_barrier.writer()
        if artifact_reference_barrier is not None
        else nullcontext()
    )
    with lease:
        artifact = persist_query_engine_evidence(
            store,
            project_id=project_id,
            run_id=run_id,
            attempt_id=attempt_id,
            query_evidence=evidence,
            status=status,
            output={
                "row_count": len(rows),
                "columns": list(columns or ()),
                "rows": [list(row) for row in rows],
            },
        )
        if evidence_reference_store is not None:
            evidence_reference_store.record(
                project_id=project_id,
                run_id=run_id,
                attempt_id=attempt_id,
                artifact=artifact,
            )
    next_cursor: str | None = None
    if result_page is not None:
        page_payload = page_query_result(
            columns=list(result_page.columns),
            rows=[list(row) for row in result_page.rows],
            digest=artifact.digest,
            page_size=page_size,
        )
        result_page = QueryResultPage(
            tuple(result_page.columns),
            tuple(tuple(row) for row in page_payload["rows"]),
        )
        next_cursor = page_payload["next_cursor"]
    return QueryExecutionResult(status, result_page, len(rows), next_cursor, artifact, selected)


__all__ = (
    "QueryEvidenceReferenceStore",
    "QueryExecutionResult",
    "QueryTransport",
    "execute_query",
)
