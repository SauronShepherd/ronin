"""Official Python SDK for the Ronin control plane."""

from __future__ import annotations

import ipaddress
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, OpenerDirector, Request, build_opener

__version__ = "0.1.0a2"

_DEFAULT_MAX_RESPONSE_BYTES = 1024 * 1024
_MAX_CURSOR_BYTES = 4096
_RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 504})
_RETRYABLE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class RoninError(Exception):
    """Base exception for the public SDK."""


class TransportError(RoninError):
    """The control plane could not be reached or returned invalid transport data."""


class ProtocolError(RoninError):
    """The control plane returned a payload that violates the SDK contract."""


@dataclass(frozen=True, slots=True)
class APIError(RoninError):
    """The control plane returned a non-success HTTP response."""

    status_code: int
    message: str
    code: str | None = None

    def __str__(self) -> str:
        suffix = f" [{self.code}]" if self.code else ""
        return f"Ronin API error {self.status_code}{suffix}: {self.message}"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    @property
    def terminal(self) -> bool:
        return self in {self.CANCELLED, self.SUCCEEDED, self.FAILED}


@dataclass(frozen=True, slots=True)
class Job:
    id: str
    state: JobState
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class JobPage:
    items: tuple[Job, ...]
    next_cursor: str | None = None


@dataclass(frozen=True, slots=True)
class JobEvent:
    sequence: int
    attempt_id: str
    attempt_sequence: int
    kind: str
    message: str
    occurred_at: str


@dataclass(frozen=True, slots=True)
class JobEventPage:
    items: tuple[JobEvent, ...]
    next_since: str


class Transport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
        query: Mapping[str, str] | None = None,
    ) -> object: ...


class _Readable(Protocol):
    def read(self, size: int = -1) -> bytes: ...


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return


def _is_loopback_host(hostname: str | None) -> bool:
    if hostname is None:
        return False
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _read_bounded(stream: _Readable, max_bytes: int) -> bytes:
    body = stream.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise TransportError("Ronin response exceeded configured byte limit")
    return body


def _api_error_code(body: bytes) -> str | None:
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    code = payload.get("code")
    if isinstance(code, str) and code and len(code) <= 128:
        return code
    error = payload.get("error")
    if isinstance(error, dict):
        nested = error.get("code")
        if isinstance(nested, str) and nested and len(nested) <= 128:
            return nested
    return None


def _request_is_retry_safe(method: str, headers: Mapping[str, str]) -> bool:
    upper = method.upper()
    if upper in _RETRYABLE_METHODS:
        return True
    if upper == "POST":
        return any(key.casefold() == "idempotency-key" for key in headers)
    return False


def _validate_cursor(value: str | None, *, name: str) -> None:
    if value is not None and (
        not value or value != value.strip() or len(value.encode("utf-8")) > _MAX_CURSOR_BYTES
    ):
        raise ValueError(f"{name} must be non-empty, trimmed, and within the byte limit")


@dataclass(frozen=True, slots=True)
class HTTPTransport:
    base_url: str
    token: str | None = None
    timeout: float = 30.0
    max_response_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES
    allow_insecure_localhost: bool = False
    max_retries: int = 2
    backoff_seconds: float = 0.1
    _opener: OpenerDirector = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.base_url.strip() or self.base_url.strip() != self.base_url:
            raise ValueError("base_url must be non-empty and trimmed")
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
            raise ValueError("base_url must be an absolute http(s) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("base_url must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("base_url must not contain query or fragment components")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.backoff_seconds < 0:
            raise ValueError("backoff_seconds must be non-negative")
        if self.token is not None:
            if not self.token or self.token.strip() != self.token:
                raise ValueError("token must be non-empty and trimmed when supplied")
            insecure_loopback = (
                parsed.scheme == "http"
                and self.allow_insecure_localhost
                and _is_loopback_host(parsed.hostname)
            )
            if parsed.scheme != "https" and not insecure_loopback:
                raise ValueError(
                    "authenticated HTTP requires HTTPS; insecure transport is allowed only for "
                    "explicit loopback development"
                )
        object.__setattr__(self, "_opener", build_opener(_RejectRedirects()))

    def _sleep_before_retry(self, attempt: int) -> None:
        if self.backoff_seconds:
            time.sleep(self.backoff_seconds * (2**attempt))

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
        query: Mapping[str, str] | None = None,
    ) -> object:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("path must be an origin-relative absolute path")
        url = self.base_url.rstrip("/") + path
        if query:
            url += "?" + urlencode(query)
        request_headers = {"Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        if self.token:
            request_headers["Authorization"] = f"Bearer {self.token}"
        data = None
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
            data = json.dumps(dict(payload), separators=(",", ":")).encode("utf-8")
        retry_safe = _request_is_retry_safe(method, request_headers)

        for attempt in range(self.max_retries + 1):
            request = Request(url, data=data, headers=request_headers, method=method)  # noqa: S310
            try:
                with self._opener.open(request, timeout=self.timeout) as response:  # noqa: S310
                    body = _read_bounded(response, self.max_response_bytes)
            except HTTPError as exc:
                try:
                    error_body = _read_bounded(exc, self.max_response_bytes)
                except TransportError as limit_error:
                    raise APIError(
                        exc.code,
                        "error response exceeded configured byte limit",
                    ) from limit_error
                if (
                    retry_safe
                    and exc.code in _RETRYABLE_STATUS_CODES
                    and attempt < self.max_retries
                ):
                    self._sleep_before_retry(attempt)
                    continue
                raise APIError(exc.code, "request failed", _api_error_code(error_body)) from exc
            except URLError as exc:
                if retry_safe and attempt < self.max_retries:
                    self._sleep_before_retry(attempt)
                    continue
                raise TransportError("Ronin endpoint unavailable") from exc
            if not body:
                return None
            try:
                return json.loads(body)
            except json.JSONDecodeError as exc:
                raise TransportError("Ronin endpoint returned invalid JSON") from exc
        raise AssertionError("unreachable retry loop")


class Ronin:
    """Synchronous client for Ronin job-control APIs."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        token: str | None = None,
        transport: Transport | None = None,
    ) -> None:
        if transport is not None and base_url is not None:
            raise ValueError("base_url and transport are mutually exclusive")
        if transport is None:
            if base_url is None:
                raise ValueError("base_url is required when transport is not supplied")
            transport = HTTPTransport(base_url, token)
        self._transport = transport

    def submit(
        self,
        *,
        project: str,
        target: str,
        parameters: Mapping[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> JobHandle:
        if not project.strip():
            raise ValueError("project must be non-empty")
        if not target.strip():
            raise ValueError("target must be non-empty")
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        payload = self._transport.request(
            "POST",
            "/v1/jobs",
            payload={
                "project": project,
                "target": target,
                "parameters": dict(parameters or {}),
            },
            headers=headers,
        )
        job = _parse_job(payload)
        return JobHandle(self, job.id)

    def get_job(self, job_id: str) -> Job:
        return _parse_job(self._transport.request("GET", f"/v1/jobs/{quote(job_id, safe='')}"))

    def list_jobs(
        self,
        *,
        project: str | None = None,
        state: JobState | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> JobPage:
        query: dict[str, str] = {"limit": str(limit)}
        if project is not None:
            if not project.strip():
                raise ValueError("project must be non-empty when supplied")
            query["project"] = project
        if state is not None:
            query["state"] = state.value
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        _validate_cursor(cursor, name="cursor")
        if cursor is not None:
            query["cursor"] = cursor
        return _parse_job_page(self._transport.request("GET", "/v1/jobs", query=query))

    def get_events(
        self,
        job_id: str,
        *,
        since: str | None = None,
        limit: int = 50,
    ) -> JobEventPage:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        _validate_cursor(since, name="since")
        query = {"limit": str(limit)}
        if since is not None:
            query["since"] = since
        return _parse_event_page(
            self._transport.request(
                "GET",
                f"/v1/jobs/{quote(job_id, safe='')}/events",
                query=query,
            )
        )

    def _cancel_job(self, job_id: str) -> Job:
        return _parse_job(
            self._transport.request("POST", f"/v1/jobs/{quote(job_id, safe='')}/cancel")
        )


@dataclass(frozen=True, slots=True)
class JobHandle:
    client: Ronin
    id: str

    def status(self) -> JobState:
        return self.client.get_job(self.id).state

    def wait(self, *, poll_interval: float = 1.0, timeout: float | None = None) -> Job:
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be positive")
        started = time.monotonic()
        while True:
            job = self.client.get_job(self.id)
            if job.state.terminal:
                return job
            if timeout is not None and time.monotonic() - started >= timeout:
                raise TimeoutError(f"Timed out waiting for Ronin job {self.id}")
            time.sleep(poll_interval)

    def cancel(self) -> Job:
        return self.client._cancel_job(self.id)

    def events(self, *, since: str | None = None, limit: int = 50) -> JobEventPage:
        return self.client.get_events(self.id, since=since, limit=limit)


def _parse_job(payload: object) -> Job:
    if not isinstance(payload, dict):
        raise ProtocolError("Expected a job object")
    try:
        job_id = payload["id"]
        state = payload["state"]
    except KeyError as exc:
        raise ProtocolError(f"Job payload missing {exc.args[0]!r}") from exc
    if not isinstance(job_id, str) or not job_id:
        raise ProtocolError("Job id must be a non-empty string")
    if not isinstance(state, str):
        raise ProtocolError("Job state must be a string")
    try:
        job_state = JobState(state)
    except ValueError as exc:
        raise ProtocolError(f"Unknown job state {state!r}") from exc
    failure_code = payload.get("failure_code")
    if failure_code is not None and not isinstance(failure_code, str):
        raise ProtocolError("failure_code must be a string when present")
    return Job(job_id, job_state, failure_code)


def _parse_job_page(payload: object) -> JobPage:
    if not isinstance(payload, dict):
        raise ProtocolError("Expected a job page object")
    if set(payload) != {"items", "next_cursor"}:
        raise ProtocolError("Job page must contain exactly items and next_cursor")
    items = payload["items"]
    next_cursor = payload["next_cursor"]
    if not isinstance(items, list):
        raise ProtocolError("Job page items must be a list")
    if next_cursor is not None and (not isinstance(next_cursor, str) or not next_cursor):
        raise ProtocolError("next_cursor must be a non-empty string when present")
    return JobPage(tuple(_parse_job(item) for item in items), next_cursor)


def _parse_event(payload: object) -> JobEvent:
    if not isinstance(payload, dict):
        raise ProtocolError("Expected a job event object")
    expected = {"sequence", "attempt_id", "attempt_sequence", "kind", "message", "occurred_at"}
    if set(payload) != expected:
        raise ProtocolError("Job event fields do not match the event contract")
    sequence = payload["sequence"]
    attempt_id = payload["attempt_id"]
    attempt_sequence = payload["attempt_sequence"]
    kind = payload["kind"]
    message = payload["message"]
    occurred_at = payload["occurred_at"]
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise ProtocolError("Job event sequence must be a non-negative integer")
    if not isinstance(attempt_id, str) or not attempt_id:
        raise ProtocolError("Job event attempt_id must be a non-empty string")
    if (
        not isinstance(attempt_sequence, int)
        or isinstance(attempt_sequence, bool)
        or attempt_sequence < 0
    ):
        raise ProtocolError("Job event attempt_sequence must be a non-negative integer")
    if not isinstance(kind, str) or not kind:
        raise ProtocolError("Job event kind must be a non-empty string")
    if not isinstance(message, str):
        raise ProtocolError("Job event message must be a string")
    if not isinstance(occurred_at, str) or not occurred_at:
        raise ProtocolError("Job event occurred_at must be a non-empty string")
    return JobEvent(sequence, attempt_id, attempt_sequence, kind, message, occurred_at)


def _parse_event_page(payload: object) -> JobEventPage:
    if not isinstance(payload, dict):
        raise ProtocolError("Expected a job event page object")
    if set(payload) != {"items", "next_since"}:
        raise ProtocolError("Job event page must contain exactly items and next_since")
    items = payload["items"]
    next_since = payload["next_since"]
    if not isinstance(items, list):
        raise ProtocolError("Job event page items must be a list")
    if not isinstance(next_since, str) or not next_since:
        raise ProtocolError("next_since must be a non-empty string")
    return JobEventPage(tuple(_parse_event(item) for item in items), next_since)


__all__ = [
    "APIError",
    "HTTPTransport",
    "Job",
    "JobEvent",
    "JobEventPage",
    "JobHandle",
    "JobPage",
    "JobState",
    "ProtocolError",
    "Ronin",
    "RoninError",
    "Transport",
    "TransportError",
    "__version__",
]
