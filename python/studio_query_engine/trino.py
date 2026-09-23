"""Bounded Trino HTTP transport mapped to Ronin query-engine contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin, urlsplit

from .contracts import CancellationResult, QueryHandle, QueryRequest, QueryResultPage, QueryStatus


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

    def submit(self, request: QueryRequest) -> tuple[QueryHandle, str]:
        response = self._client.request(
            "POST", urljoin(self._base_url, "v1/statement"), body=request.sql
        )
        query_id = _text(response.get("id"), "id")
        next_uri = _safe_uri(response.get("nextUri"), base_url=self._base_url, name="nextUri")
        self._max_rows[query_id] = request.max_rows
        return QueryHandle(query_id, self._provider_id, provider_query_id=query_id), next_uri

    def poll(
        self, handle: QueryHandle, next_uri: str
    ) -> tuple[QueryStatus, QueryResultPage | None, str | None]:
        if handle.provider_id != self._provider_id:
            raise QueryFailure("provider_mismatch", "query handle belongs to another provider")
        next_uri = _safe_uri(next_uri, base_url=self._base_url, name="nextUri")
        response = self._client.request("GET", next_uri)
        if response.get("error") is not None:
            error = response["error"]
            if isinstance(error, Mapping):
                message = str(error.get("message", "provider query failed"))
            else:
                message = "provider query failed"
            return QueryStatus("failed", message, handle.provider_query_id), None, None
        next_page = response.get("nextUri")
        page = self._result_page(response, max_rows=self._max_rows.get(handle.query_id, 1_000_000))
        if page is not None:
            if next_page is not None:
                return (
                    QueryStatus("running", provider_query_id=handle.provider_query_id),
                    page,
                    _safe_uri(next_page, base_url=self._base_url, name="nextUri"),
                )
            return (
                QueryStatus("succeeded", provider_query_id=handle.provider_query_id),
                page,
                None,
            )
        if next_page is None:
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
        cancelled = response.get("cancelled", True)
        if not isinstance(cancelled, bool):
            raise QueryFailure("invalid_provider_response", "cancelled must be boolean")
        return CancellationResult(cancelled, "cancelled" if cancelled else "running")

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


__all__ = ("HttpClient", "QueryFailure", "TrinoHttpTransport")
