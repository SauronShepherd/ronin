"""Minimal v0.1 HTTP adapter over the shared durable execution service.

This module owns transport concerns only. Canonical lifecycle and storage semantics
remain in ``studio_orchestrator`` / ``studio_execution``; the HTTP boundary maps
JSON requests to those existing contracts without introducing framework models.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from collections.abc import Coroutine
from concurrent.futures import Future
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from typing import Any, cast
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4

from studio_execution import DurableExecutionService
from studio_orchestrator import Instant, Job, JobId, JobState, Page, Run, RunId, RunState
from studio_storage import IdempotencyConflict, StorageBackpressureError

_MAX_REQUEST_BYTES = 1024 * 1024
_MAX_CURSOR_BYTES = 4096
_MAX_LIST_LIMIT = 100
_DEFAULT_LIST_LIMIT = 50
SUPPORTED_ROUTES = frozenset(
    {
        ("POST", "/v1/jobs"),
        ("GET", "/v1/jobs"),
        ("GET", "/v1/jobs/{job_id}"),
        ("POST", "/v1/jobs/{job_id}/cancel"),
    }
)


def _now() -> Instant:
    return Instant(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))


def _request_identity(
    project: str,
    target: str,
    parameters: dict[str, object],
) -> tuple[str, str]:
    parameters_json = json.dumps(
        parameters,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    request_json = json.dumps(
        {"parameters": parameters, "project": project, "target": target},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return parameters_json, hashlib.sha256(request_json.encode("utf-8")).hexdigest()


def _job_payload(job: Job) -> dict[str, object]:
    return {
        "id": str(job.id),
        "state": job.state.value,
        "failure_code": job.failure_code,
    }


def _page_payload(page: Page) -> dict[str, object]:
    return {
        "items": [_job_payload(job) for job in page.items],
        "next_cursor": page.next_cursor,
    }


def _single_query_values(query: str) -> dict[str, str]:
    parsed = parse_qs(query, keep_blank_values=True, strict_parsing=False)
    allowed = {"project", "state", "limit", "cursor"}
    unknown = set(parsed) - allowed
    if unknown:
        raise ValueError(f"unknown query parameter: {sorted(unknown)[0]}")
    values: dict[str, str] = {}
    for key, candidates in parsed.items():
        if len(candidates) != 1:
            raise ValueError(f"query parameter {key} must appear at most once")
        values[key] = candidates[0]
    return values


class _ServiceLoop:
    """Own one asyncio loop for the bounded async service across HTTP threads."""

    def __init__(self, service: DurableExecutionService) -> None:
        self._service = service
        self._loop = asyncio.new_event_loop()
        self._ready = Event()
        self._thread = Thread(target=self._run, name="ronin-http-service", daemon=True)
        self._thread.start()
        self._ready.wait()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    def call(self, coroutine: Coroutine[Any, Any, Any]) -> Any:
        future: Future[Any] = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        return future.result()

    def close(self) -> None:
        if not self._thread.is_alive():
            return
        self.call(self._service.aclose())
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()
        self._loop.close()


class DurableHTTPApplication:
    """Transport mapping for the implemented frozen v0.1 job-control endpoints."""

    def __init__(self, service: DurableExecutionService) -> None:
        self._service = service
        self._loop = _ServiceLoop(service)

    def close(self) -> None:
        self._loop.close()

    def submit(
        self,
        payload: object,
        *,
        idempotency_key: str | None,
    ) -> tuple[HTTPStatus, dict[str, object]]:
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        if set(payload) - {"project", "target", "parameters"}:
            raise ValueError("request body contains unknown fields")
        project = payload.get("project")
        target = payload.get("target")
        parameters = payload.get("parameters", {})
        if not isinstance(project, str) or not project.strip() or project != project.strip():
            raise ValueError("project must be a non-empty trimmed string")
        if not isinstance(target, str) or not target.strip() or target != target.strip():
            raise ValueError("target must be a non-empty trimmed string")
        if not isinstance(parameters, dict) or not all(isinstance(key, str) for key in parameters):
            raise ValueError("parameters must be a JSON object with string keys")
        if idempotency_key is not None and (
            not idempotency_key
            or idempotency_key != idempotency_key.strip()
            or len(idempotency_key) > 256
        ):
            raise ValueError(
                "Idempotency-Key must be non-empty, trimmed, and at most 256 characters"
            )

        parameters_dict = cast(dict[str, object], parameters)
        parameters_json, request_digest = _request_identity(project, target, parameters_dict)
        now = _now()
        job_id = JobId(f"job-{uuid4().hex}")
        run_id = RunId(f"run-{uuid4().hex}")
        key = idempotency_key or f"generated-{uuid4().hex}"
        candidate = Job(
            id=job_id,
            project_id=project,
            idempotency_key=key,
            request_digest=request_digest,
            state=JobState.QUEUED,
            created_at=now,
            updated_at=now,
            target=target,
            parameters_json=parameters_json,
        )
        run = Run(
            id=run_id,
            job_id=job_id,
            ordinal=1,
            state=RunState.PENDING,
            not_before=now,
            created_at=now,
            updated_at=now,
        )
        stored = cast(Job, self._loop.call(self._service.submit(candidate, run)))
        status = HTTPStatus.CREATED if stored.id == candidate.id else HTTPStatus.OK
        return status, _job_payload(stored)

    def status(self, job_id: str) -> dict[str, object] | None:
        job = cast(Job | None, self._loop.call(self._service.status(JobId(job_id))))
        return None if job is None else _job_payload(job)

    def list_jobs(
        self,
        *,
        project: str | None,
        state: str | None,
        limit: str | None,
        cursor: str | None,
    ) -> dict[str, object]:
        if project is not None and (
            not project or project != project.strip() or len(project) > 256
        ):
            raise ValueError("project must be non-empty, trimmed, and at most 256 characters")
        job_state = None
        if state is not None:
            try:
                job_state = JobState(state)
            except ValueError as exc:
                raise ValueError("state is invalid") from exc
        page_limit = _DEFAULT_LIST_LIMIT
        if limit is not None:
            try:
                page_limit = int(limit)
            except ValueError as exc:
                raise ValueError("limit must be an integer") from exc
            if not 1 <= page_limit <= _MAX_LIST_LIMIT:
                raise ValueError(f"limit must be between 1 and {_MAX_LIST_LIMIT}")
        if cursor is not None and (
            not cursor
            or cursor != cursor.strip()
            or len(cursor.encode("utf-8")) > _MAX_CURSOR_BYTES
        ):
            raise ValueError("cursor must be non-empty, trimmed, and within the byte limit")
        page = cast(
            Page,
            self._loop.call(
                self._service.list_jobs(
                    project_id=project,
                    state=job_state,
                    limit=page_limit,
                    cursor=cursor,
                )
            ),
        )
        return _page_payload(page)

    def cancel(self, job_id: str) -> dict[str, object]:
        job = cast(Job, self._loop.call(self._service.cancel(JobId(job_id), now=_now())))
        return _job_payload(job)


class RoninHTTPServer(ThreadingHTTPServer):
    """Standard-library HTTP server that owns one shared service-loop bridge."""

    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        service: DurableExecutionService,
        *,
        token: str,
    ) -> None:
        if not token or token != token.strip() or "\n" in token or "\r" in token:
            raise ValueError("token must be non-empty, trimmed, and single-line")
        self.application = DurableHTTPApplication(service)
        self._token = token
        try:
            super().__init__(server_address, _Handler)
        except BaseException:
            self.application.close()
            raise

    def authorized(self, authorization: str | None) -> bool:
        prefix = "Bearer "
        return (
            authorization is not None
            and authorization.startswith(prefix)
            and hmac.compare_digest(authorization[len(prefix) :], self._token)
        )

    def server_close(self) -> None:
        try:
            super().server_close()
        finally:
            self.application.close()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *args: object) -> None:
        del args

    def _ronin_server(self) -> RoninHTTPServer:
        return cast(RoninHTTPServer, self.server)

    def _write_json(self, status: HTTPStatus, payload: object) -> None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, code: str, message: str) -> None:
        self._write_json(status, {"error": {"code": code, "message": message}})

    def _require_auth(self) -> bool:
        if self._ronin_server().authorized(self.headers.get("Authorization")):
            return True
        self._error(HTTPStatus.UNAUTHORIZED, "unauthorized", "valid bearer authorization required")
        return False

    def _read_json(self) -> object:
        length_header = self.headers.get("Content-Length")
        if length_header is None:
            raise ValueError("Content-Length is required")
        try:
            length = int(length_header)
        except ValueError as exc:
            raise ValueError("Content-Length must be an integer") from exc
        if length < 0 or length > _MAX_REQUEST_BYTES:
            raise ValueError("request body exceeds configured byte limit")
        body = self.rfile.read(length)
        try:
            return json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("request body must be valid UTF-8 JSON") from exc

    def do_POST(self) -> None:  # noqa: N802
        if not self._require_auth():
            return
        split = urlsplit(self.path)
        path = split.path
        if path == "/v1/jobs":
            if split.query:
                self._error(
                    HTTPStatus.BAD_REQUEST, "invalid_request", "submit does not accept query"
                )
                return
            try:
                status, payload = self._ronin_server().application.submit(
                    self._read_json(),
                    idempotency_key=self.headers.get("Idempotency-Key"),
                )
            except IdempotencyConflict:
                self._error(
                    HTTPStatus.CONFLICT,
                    "idempotency_conflict",
                    "idempotency key already exists for a different request",
                )
                return
            except StorageBackpressureError:
                self._error(
                    HTTPStatus.SERVICE_UNAVAILABLE, "storage_backpressure", "server is busy"
                )
                return
            except ValueError as exc:
                self._error(HTTPStatus.BAD_REQUEST, "invalid_request", str(exc))
                return
            self._write_json(status, payload)
            return

        prefix = "/v1/jobs/"
        suffix = "/cancel"
        if not path.startswith(prefix) or not path.endswith(suffix):
            self._error(HTTPStatus.NOT_FOUND, "not_found", "route not found")
            return
        encoded_job_id = path[len(prefix) : -len(suffix)]
        if not encoded_job_id or "/" in encoded_job_id or split.query:
            self._error(HTTPStatus.NOT_FOUND, "not_found", "route not found")
            return
        try:
            job_id = unquote(encoded_job_id, errors="strict")
            payload = self._ronin_server().application.cancel(job_id)
        except KeyError:
            self._error(HTTPStatus.NOT_FOUND, "job_not_found", "job does not exist")
            return
        except StorageBackpressureError:
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, "storage_backpressure", "server is busy")
            return
        except (UnicodeError, ValueError):
            self._error(HTTPStatus.BAD_REQUEST, "invalid_job_id", "job id is invalid")
            return
        self._write_json(HTTPStatus.OK, payload)

    def do_GET(self) -> None:  # noqa: N802
        if not self._require_auth():
            return
        split = urlsplit(self.path)
        path = split.path
        if path == "/v1/jobs":
            try:
                query = _single_query_values(split.query)
                payload = self._ronin_server().application.list_jobs(
                    project=query.get("project"),
                    state=query.get("state"),
                    limit=query.get("limit"),
                    cursor=query.get("cursor"),
                )
            except StorageBackpressureError:
                self._error(
                    HTTPStatus.SERVICE_UNAVAILABLE, "storage_backpressure", "server is busy"
                )
                return
            except ValueError as exc:
                self._error(HTTPStatus.BAD_REQUEST, "invalid_request", str(exc))
                return
            self._write_json(HTTPStatus.OK, payload)
            return

        prefix = "/v1/jobs/"
        if not path.startswith(prefix) or path == prefix:
            self._error(HTTPStatus.NOT_FOUND, "not_found", "route not found")
            return
        encoded_job_id = path[len(prefix) :]
        if "/" in encoded_job_id or split.query:
            self._error(HTTPStatus.NOT_FOUND, "not_found", "route not found")
            return
        try:
            job_id = unquote(encoded_job_id, errors="strict")
            payload = self._ronin_server().application.status(job_id)
        except StorageBackpressureError:
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, "storage_backpressure", "server is busy")
            return
        except (UnicodeError, ValueError):
            self._error(HTTPStatus.BAD_REQUEST, "invalid_job_id", "job id is invalid")
            return
        if payload is None:
            self._error(HTTPStatus.NOT_FOUND, "job_not_found", "job does not exist")
            return
        self._write_json(HTTPStatus.OK, payload)


__all__ = (
    "DurableHTTPApplication",
    "RoninHTTPServer",
    "SUPPORTED_ROUTES",
)
