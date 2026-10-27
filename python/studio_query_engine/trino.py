"""Bounded Trino HTTP transport mapped to Ronin query-engine contracts."""

from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin, urlsplit

from .contracts import (
    CancellationResult,
    QueryHandle,
    QueryRequest,
    QueryResultPage,
    QueryState,
    QueryStatus,
)


class HttpClient(Protocol):
    def request(
        self, method: str, url: str, *, body: str | None = None
    ) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class QueryFailure(RuntimeError):
    """Normalized provider failure safe to expose at the Ronin boundary."""

    code: str
    message: str

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QueryFailure("invalid_provider_response", f"provider response lacks {name}")
    return value


def _safe_uri(value: object, *, base_url: str, name: str) -> str:
    uri = _text(value, name)
    expected = urlsplit(base_url)
    actual = urlsplit(uri)
    if actual.scheme not in {"http", "https"} or actual.username or actual.password:
        raise QueryFailure("unsafe_provider_uri", f"provider {name} is not a safe HTTP URI")
    if (actual.scheme, actual.hostname, actual.port) != (
        expected.scheme,
        expected.hostname,
        expected.port,
    ):
        raise QueryFailure("unsafe_provider_uri", f"provider {name} escaped the configured origin")
    return uri


class TrinoHttpTransport:
    """Submit and poll Trino statements without exposing provider response types."""

    def __init__(self, client: HttpClient, *, base_url: str, provider_id: str = "trino") -> None:
        if not base_url or not base_url.endswith("/"):
            raise ValueError("base_url must be a non-empty URL ending with '/'")
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("base_url must be an HTTP(S) URL")
        if parsed.username or parsed.password:
            raise ValueError("base_url must not contain credentials")
        if not provider_id.strip():
            raise ValueError("provider_id must be non-empty")
        self._client = client
        self._base_url = base_url
        self._provider_id = provider_id
        self._max_rows: dict[str, int] = {}
        self._rows_seen: dict[str, int] = {}
        self._initial_responses: dict[
            str, tuple[QueryStatus, QueryResultPage | None, str | None]
        ] = {}

    def submit(self, request: QueryRequest) -> tuple[QueryHandle, str]:
        statement = _prepared_select(request)
        response = self._client.request(
            "POST", urljoin(self._base_url, "v1/statement"), body=statement
        )
        query_id = _text(response.get("id"), "id")
        next_value = response.get("nextUri")
        next_uri = (
            _safe_uri(next_value, base_url=self._base_url, name="nextUri")
            if next_value is not None
            else None
        )
        if response.get("error") is not None:
            error = response["error"]
            message = (
                str(error.get("message", "provider query failed"))
                if isinstance(error, Mapping)
                else "provider query failed"
            )
            self._initial_responses[query_id] = (
                QueryStatus("failed", message, query_id),
                None,
                None,
            )
            return QueryHandle(query_id, self._provider_id, provider_query_id=query_id), ""

        initial_page = self._result_page(response, max_rows=request.max_rows)
        if initial_page is not None and len(initial_page.rows) > request.max_rows:
            raise QueryFailure("result_limit_exceeded", "provider returned too many rows")
        has_initial_result = initial_page is not None or next_uri is None
        self._max_rows[query_id] = request.max_rows
        self._rows_seen[query_id] = len(initial_page.rows) if initial_page is not None else 0
        if has_initial_result:
            state: QueryState = "running" if next_uri is not None else "succeeded"
            self._initial_responses[query_id] = (
                QueryStatus(state, provider_query_id=query_id),
                initial_page,
                next_uri,
            )
        return QueryHandle(query_id, self._provider_id, provider_query_id=query_id), next_uri or ""

    def poll(
        self, handle: QueryHandle, next_uri: str
    ) -> tuple[QueryStatus, QueryResultPage | None, str | None]:
        if handle.provider_id != self._provider_id:
            raise QueryFailure("provider_mismatch", "query handle belongs to another provider")
        initial = self._initial_responses.pop(handle.query_id, None)
        if initial is not None:
            status, page, following_uri = initial
            if status.state in {"succeeded", "failed", "cancelled"}:
                self._forget(handle.query_id)
            return status, page, following_uri
        next_uri = _safe_uri(next_uri, base_url=self._base_url, name="nextUri")
        response = self._client.request("GET", next_uri)
        if response.get("error") is not None:
            error = response["error"]
            if isinstance(error, Mapping):
                message = str(error.get("message", "provider query failed"))
            else:
                message = "provider query failed"
            self._forget(handle.query_id)
            return QueryStatus("failed", message, handle.provider_query_id), None, None
        next_page = response.get("nextUri")
        page = self._result_page(response, max_rows=self._max_rows.get(handle.query_id, 1_000_000))
        if page is not None:
            max_rows = self._max_rows.get(handle.query_id, 1_000_000)
            seen = self._rows_seen.get(handle.query_id, 0)
            if seen + len(page.rows) > max_rows:
                self._forget(handle.query_id)
                raise QueryFailure("result_limit_exceeded", "provider returned too many rows")
            self._rows_seen[handle.query_id] = seen + len(page.rows)
            if next_page is not None:
                return (
                    QueryStatus("running", provider_query_id=handle.provider_query_id),
                    page,
                    _safe_uri(next_page, base_url=self._base_url, name="nextUri"),
                )
            self._forget(handle.query_id)
            return (
                QueryStatus("succeeded", provider_query_id=handle.provider_query_id),
                page,
                None,
            )
        if next_page is None:
            self._forget(handle.query_id)
            return QueryStatus("succeeded", provider_query_id=handle.provider_query_id), None, None
        return (
            QueryStatus("running", provider_query_id=handle.provider_query_id),
            None,
            _safe_uri(next_page, base_url=self._base_url, name="nextUri"),
        )

    def cancel(self, handle: QueryHandle, cancel_uri: str | None = None) -> CancellationResult:
        if handle.provider_id != self._provider_id:
            raise QueryFailure("provider_mismatch", "query handle belongs to another provider")
        uri = cancel_uri or urljoin(
            self._base_url, f"v1/query/{handle.provider_query_id or handle.query_id}"
        )
        uri = _safe_uri(uri, base_url=self._base_url, name="cancel URI")
        response = self._client.request("DELETE", uri)
        cancelled = response.get("cancelled")
        if not isinstance(cancelled, bool):
            raise QueryFailure(
                "invalid_provider_response", "cancel response must declare boolean cancelled"
            )
        if cancelled:
            self._forget(handle.query_id)
        return CancellationResult(cancelled, "cancelled" if cancelled else "running")

    def _forget(self, query_id: str) -> None:
        self._initial_responses.pop(query_id, None)
        self._max_rows.pop(query_id, None)
        self._rows_seen.pop(query_id, None)

    @staticmethod
    def _result_page(response: Mapping[str, object], *, max_rows: int) -> QueryResultPage | None:
        raw_data = response.get("data")
        if raw_data is None:
            return None
        if not isinstance(raw_data, Sequence) or isinstance(raw_data, (str, bytes)):
            raise QueryFailure("invalid_provider_response", "data must be an array")
        raw_columns = response.get("columns", ())
        if not isinstance(raw_columns, Sequence) or isinstance(raw_columns, (str, bytes)):
            raise QueryFailure("invalid_provider_response", "columns must be an array")
        names: list[str] = []
        for column in raw_columns:
            if not isinstance(column, Mapping):
                raise QueryFailure("invalid_provider_response", "column must be an object")
            names.append(_text(column.get("name"), "column name"))
        rows: list[tuple[object, ...]] = []
        for row in raw_data:
            if not isinstance(row, Sequence) or isinstance(row, (str, bytes)):
                raise QueryFailure("invalid_provider_response", "row must be an array")
            rows.append(tuple(row))
        if len(rows) > max_rows:
            raise QueryFailure("result_limit_exceeded", "provider returned too many rows")
        try:
            return QueryResultPage(tuple(names), tuple(rows))
        except ValueError as exc:
            raise QueryFailure("invalid_provider_response", str(exc)) from exc


def _prepared_select(request: QueryRequest) -> str:
    """Wrap a validated SELECT as a Trino prepared execution with typed values.

    EXECUTE IMMEDIATE keeps the SQL text as a quoted statement string and sends
    each parameter as a separately serialized SQL expression. String values are
    UTF-8/base64 encoded so their bytes cannot escape a SQL literal.
    """
    if not request.parameters:
        return request.sql

    values: list[str] = []
    for value in request.parameters:
        if value is None:
            values.append("NULL")
        elif isinstance(value, bool):
            values.append("TRUE" if value else "FALSE")
        elif isinstance(value, int):
            values.append(str(value))
        elif isinstance(value, float):
            values.append(f"CAST({value!r} AS DOUBLE)")
        elif isinstance(value, str):
            encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
            values.append(f"from_utf8(from_base64('{encoded}'))")
        else:  # QueryRequest validation makes this unreachable; keep the boundary fail-closed.
            raise QueryFailure("invalid_parameter", "query parameter is not a supported scalar")

    escaped_sql = request.sql.replace("'", "''")
    return f"EXECUTE IMMEDIATE '{escaped_sql}' USING {', '.join(values)}"


__all__ = ("HttpClient", "QueryFailure", "TrinoHttpTransport")
