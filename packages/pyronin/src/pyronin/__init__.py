"""Official Python SDK for the Ronin control plane."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

__version__ = "0.1.0a1"


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

    def __str__(self) -> str:
        return f"Ronin API error {self.status_code}: {self.message}"


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
class JobEvent:
    sequence: int
    kind: str
    message: str


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


@dataclass(frozen=True, slots=True)
class HTTPTransport:
    base_url: str
    token: str | None = None
    timeout: float = 30.0

    def __post_init__(self) -> None:
        if not self.base_url.strip():
            raise ValueError("base_url must be non-empty")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
        query: Mapping[str, str] | None = None,
    ) -> object:
        url = self.base_url.rstrip("/") + path
        if query:
            url += "?" + urlencode(query)
        request_headers = {"Accept": "application/json"}
        if self.token:
            request_headers["Authorization"] = f"Bearer {self.token}"
        if headers:
            request_headers.update(headers)
        data = None
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
            data = json.dumps(dict(payload), separators=(",", ":")).encode("utf-8")
        request = Request(url, data=data, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                body = response.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace").strip()
            raise APIError(exc.code, body or exc.reason) from exc
        except URLError as exc:
            raise TransportError(f"Ronin endpoint unavailable: {exc.reason}") from exc
        if not body:
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise TransportError("Ronin endpoint returned invalid JSON") from exc


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
        return _parse_job(self._transport.request("GET", _job_path(job_id)))

    def list_jobs(self, *, state: JobState | None = None) -> tuple[Job, ...]:
        query = {"state": state.value} if state is not None else None
        payload = self._transport.request("GET", "/v1/jobs", query=query)
        if not isinstance(payload, list):
            raise ProtocolError("job list must be a JSON array")
        return tuple(_parse_job(item) for item in payload)

    def _cancel(self, job_id: str) -> Job:
        return _parse_job(self._transport.request("POST", f"{_job_path(job_id)}/cancel"))

    def _events(self, job_id: str) -> tuple[JobEvent, ...]:
        payload = self._transport.request("GET", f"{_job_path(job_id)}/events")
        if not isinstance(payload, list):
            raise ProtocolError("job events must be a JSON array")
        return tuple(_parse_event(item) for item in payload)


@dataclass(frozen=True, slots=True)
class JobHandle:
    client: Ronin
    id: str

    def get(self) -> Job:
        return self.client.get_job(self.id)

    def status(self) -> JobState:
        return self.get().state

    def cancel(self) -> Job:
        return self.client._cancel(self.id)

    def events(self) -> tuple[JobEvent, ...]:
        return self.client._events(self.id)

    def wait(self, *, poll_interval: float = 1.0, timeout: float | None = None) -> Job:
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be positive")
        started = time.monotonic()
        while True:
            job = self.get()
            if job.state.terminal:
                return job
            if timeout is not None and time.monotonic() - started >= timeout:
                raise TimeoutError(f"job {self.id!r} did not reach a terminal state")
            time.sleep(poll_interval)


def _job_path(job_id: str) -> str:
    if not job_id:
        raise ValueError("job_id must be non-empty")
    return f"/v1/jobs/{quote(job_id, safe='')}"


def _parse_job(payload: object) -> Job:
    if not isinstance(payload, dict):
        raise ProtocolError("job payload must be a JSON object")
    job_id = payload.get("id")
    state_value = payload.get("state")
    failure_code = payload.get("failure_code")
    if not isinstance(job_id, str) or not job_id:
        raise ProtocolError("job id must be a non-empty string")
    if not isinstance(state_value, str):
        raise ProtocolError("job state must be a string")
    try:
        state = JobState(state_value)
    except ValueError as exc:
        raise ProtocolError(f"unknown job state: {state_value!r}") from exc
    if failure_code is not None and not isinstance(failure_code, str):
        raise ProtocolError("failure_code must be a string or null")
    return Job(job_id, state, failure_code)


def _parse_event(payload: object) -> JobEvent:
    if not isinstance(payload, dict):
        raise ProtocolError("job event must be a JSON object")
    sequence = payload.get("sequence")
    kind = payload.get("kind")
    message = payload.get("message")
    if not isinstance(sequence, int) or sequence < 0:
        raise ProtocolError("event sequence must be a non-negative integer")
    if not isinstance(kind, str) or not kind:
        raise ProtocolError("event kind must be a non-empty string")
    if not isinstance(message, str):
        raise ProtocolError("event message must be a string")
    return JobEvent(sequence, kind, message)


__all__ = [
    "APIError",
    "HTTPTransport",
    "Job",
    "JobEvent",
    "JobHandle",
    "JobState",
    "ProtocolError",
    "Ronin",
    "RoninError",
    "Transport",
    "TransportError",
    "__version__",
]
