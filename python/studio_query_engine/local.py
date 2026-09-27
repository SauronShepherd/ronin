"""Adapter for executing the shared query contract on a local SQL engine."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from studio_sql import SqlEngine

from .contracts import (
    CancellationResult,
    QueryHandle,
    QueryRequest,
    QueryResultPage,
    QueryState,
    QueryStatus,
)


@dataclass
class _PendingQuery:
    request: QueryRequest
    executed: bool = False
    cancelled: bool = False


class LocalSqlTransport:
    """Run provider-neutral query requests through an injected ``SqlEngine``.

    The adapter deliberately keeps lifecycle state in memory.  It is a local
    reference transport for the same submit/poll/cancel contract used by
    remote engines; durable orchestration remains the responsibility of the
    Data Engineering execution layer.
    """

    def __init__(self, engine: SqlEngine, *, provider_id: str = "ronin-local-sql") -> None:
        if not provider_id or provider_id != provider_id.strip():
            raise ValueError("provider_id must be non-empty and trimmed")
        self._engine = engine
        self._provider_id = provider_id
        self._pending: dict[str, _PendingQuery] = {}

    def submit(self, request: QueryRequest) -> tuple[QueryHandle, str]:
        query_id = hashlib.sha256(
            f"{self._provider_id}:{request.canonical_json()}".encode()
        ).hexdigest()
        self._pending[query_id] = _PendingQuery(request)
        return QueryHandle(query_id, self._provider_id, query_id), query_id

    def poll(
        self, handle: QueryHandle, next_uri: str
    ) -> tuple[QueryStatus, QueryResultPage | None, str | None]:
        del next_uri
        if handle.provider_id != self._provider_id:
            return QueryStatus("failed", "query handle belongs to another provider"), None, None
        pending = self._pending.get(handle.query_id)
        if pending is None:
            return QueryStatus("failed", "query handle is unknown"), None, None
        if pending.cancelled:
            return QueryStatus("cancelled", provider_query_id=handle.provider_query_id), None, None
        if pending.executed:
            return QueryStatus("succeeded", provider_query_id=handle.provider_query_id), None, None
        pending.executed = True
        try:
            result = self._engine.execute(pending.request.sql, max_rows=pending.request.max_rows)
        except Exception as exc:
            return (
                QueryStatus("failed", str(exc)[:4_000], provider_query_id=handle.provider_query_id),
                None,
                None,
            )
        page = QueryResultPage(
            tuple(column.name for column in result.columns),
            result.rows,
        )
        return QueryStatus("succeeded", provider_query_id=handle.provider_query_id), page, None

    def cancel(self, handle: QueryHandle) -> CancellationResult:
        if handle.provider_id != self._provider_id:
            return CancellationResult(False, "failed")
        pending = self._pending.get(handle.query_id)
        if pending is None or pending.executed:
            final_state: QueryState = "succeeded" if pending and pending.executed else "failed"
            return CancellationResult(False, final_state)
        if pending.cancelled:
            return CancellationResult(False, "cancelled")
        pending.cancelled = True
        return CancellationResult(True, "cancelled")


__all__ = ("LocalSqlTransport",)
