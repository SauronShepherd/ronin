"""Internal structured runner broker that owns Docker authority for Compose workers."""

from __future__ import annotations

import asyncio
import hmac
import re
import threading
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote, urlsplit

from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.canonical_json import encode as encode_canonical_json
from studio_kernel import (
    CancellationToken,
    CellExecutionRequest,
    CellExecutionResult,
    ExecutionAttemptId,
    KernelDirective,
)
from studio_notebook import CellId
from studio_runners import (
    ContainerExecutionLimits,
    ContainerExecutorConfig,
    DockerContainerKernelExecutor,
    LocalExecutionEvidenceStore,
)

_EXECUTION_ID = re.compile(r"^exec-[0-9a-f]{32}$")
_MAX_BODY_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class RunnerBrokerConfig:
    token: str
    image: str
    evidence_root: Path
    limits: ContainerExecutionLimits = field(default_factory=ContainerExecutionLimits)
    engine: str = "docker"
    engine_path: str | None = None
    request_timeout_seconds: float = 15.0
    max_body_bytes: int = _MAX_BODY_BYTES

    def __post_init__(self) -> None:
        if (
            not self.token
            or self.token != self.token.strip()
            or "\n" in self.token
            or "\r" in self.token
            or "\x00" in self.token
        ):
            raise ValueError("runner broker token must be non-empty, trimmed, and single-line")
        ContainerExecutorConfig(image=self.image, limits=self.limits, engine=self.engine)
        if self.request_timeout_seconds <= 0 or self.request_timeout_seconds > 300:
            raise ValueError("runner broker request timeout must be in (0, 300]")
        if self.max_body_bytes < 1 or self.max_body_bytes > 64 * 1024 * 1024:
            raise ValueError("runner broker body limit must be between 1 byte and 64 MiB")


class _BrokerHandler(BaseHTTPRequestHandler):
    server_version = "RoninRunnerBroker/1"
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def _broker(self) -> RunnerBrokerServer:
        return cast(RunnerBrokerServer, self.server)

    def _write_json(self, status: HTTPStatus, payload: object) -> None:
        data = encode_canonical_json(payload)
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status: HTTPStatus, code: str, message: str) -> None:
        self._write_json(status, {"code": code, "message": message})

    def _authenticate(self) -> bool:
        authorization = self.headers.get("Authorization")
        prefix = "Bearer "
        supplied = (
            ""
            if authorization is None or not authorization.startswith(prefix)
            else authorization[len(prefix) :]
        )
        if not supplied or not hmac.compare_digest(supplied, self._broker().config.token):
            self._error(
                HTTPStatus.UNAUTHORIZED,
                "unauthorized",
                "valid runner broker authorization required",
            )
            return False
        return True

    def _read_json(self) -> object | None:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            self._error(HTTPStatus.LENGTH_REQUIRED, "length_required", "Content-Length is required")
            return None
        try:
            length = int(raw_length)
        except ValueError:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request", "Content-Length is invalid")
            return None
        if length < 1 or length > self._broker().config.max_body_bytes:
            self._error(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "request_too_large",
                "runner broker request body exceeds configured limit",
            )
            return None
        data = self.rfile.read(length)
        if len(data) != length:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request", "request body is incomplete")
            return None
        try:
            return decode_canonical_json(data)
        except (TypeError, ValueError):
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request", "request body is invalid JSON")
            return None

    def _execution_id(self) -> str | None:
        split = urlsplit(self.path)
        prefix = "/v1/executions/"
        if split.query or split.fragment or not split.path.startswith(prefix):
            return None
        raw = split.path[len(prefix) :]
        try:
            execution_id = unquote(raw, errors="strict")
        except UnicodeError:
            return None
        return execution_id if _EXECUTION_ID.fullmatch(execution_id) else None

    def do_GET(self) -> None:  # noqa: N802
        split = urlsplit(self.path)
        if split.query or split.fragment:
            self._error(HTTPStatus.NOT_FOUND, "not_found", "route not found")
            return
        if split.path == "/healthz":
            self._write_json(HTTPStatus.OK, {"status": "ready"})
            return
        if split.path == "/v1/runtime":
            if not self._authenticate():
                return
            self._write_json(
                HTTPStatus.OK,
                {"version": 1, "image": self._broker().config.image},
            )
            return
        self._error(HTTPStatus.NOT_FOUND, "not_found", "route not found")

    def do_POST(self) -> None:  # noqa: N802
        if not self._authenticate():
            return
        execution_id = self._execution_id()
        if execution_id is None:
            self._error(HTTPStatus.NOT_FOUND, "not_found", "route not found")
            return
        payload = self._read_json()
        if payload is None:
            return
        try:
            attempt_id, cell = self._broker().parse_execution(payload)
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request", str(exc))
            return
        token = self._broker().begin_execution(execution_id)
        if token is None:
            self._error(
                HTTPStatus.CONFLICT,
                "execution_active",
                "runner broker execution id is already active",
            )
            return
        try:
            result = asyncio.run(self._broker().execute(attempt_id, cell, token))
        except Exception:
            self._error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "execution_unavailable",
                "runner broker execution failed before a normalized result was produced",
            )
            return
        finally:
            self._broker().finish_execution(execution_id, token)
        self._write_json(HTTPStatus.OK, self._broker().result_payload(result))

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._authenticate():
            return
        execution_id = self._execution_id()
        if execution_id is None:
            self._error(HTTPStatus.NOT_FOUND, "not_found", "route not found")
            return
        if not self._broker().cancel_execution(execution_id):
            self._error(
                HTTPStatus.NOT_FOUND,
                "execution_not_active",
                "runner broker execution is not active",
            )
            return
        self._write_json(HTTPStatus.OK, {"version": 1, "cancelled": True})

    def do_PUT(self) -> None:  # noqa: N802
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method_not_allowed", "method not allowed")

    def do_PATCH(self) -> None:  # noqa: N802
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method_not_allowed", "method not allowed")


class RunnerBrokerServer(ThreadingHTTPServer):
    """Threaded internal broker with no general Docker command surface."""

    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        config: RunnerBrokerConfig,
    ) -> None:
        self.config = config
        self._active: dict[str, CancellationToken] = {}
        self._active_lock = threading.Lock()
        config.evidence_root.mkdir(parents=True, exist_ok=True)
        super().__init__(server_address, _BrokerHandler)

    def get_request(self) -> tuple[Any, Any]:
        request, address = super().get_request()
        request.settimeout(self.config.request_timeout_seconds)
        return request, address

    @staticmethod
    def parse_execution(payload: object) -> tuple[ExecutionAttemptId, CellExecutionRequest]:
        if not isinstance(payload, dict) or set(payload) != {"version", "attempt_id", "cell"}:
            raise ValueError("runner broker request fields are invalid")
        if payload.get("version") != 1:
            raise ValueError("runner broker request version is unsupported")
        attempt_raw = payload.get("attempt_id")
        cell_raw = payload.get("cell")
        if not isinstance(attempt_raw, str):
            raise ValueError("runner broker attempt id must be a string")
        if not isinstance(cell_raw, dict) or set(cell_raw) != {
            "cell_id",
            "language",
            "executable_source",
        }:
            raise ValueError("runner broker cell fields are invalid")
        cell_id = cell_raw.get("cell_id")
        language = cell_raw.get("language")
        source = cell_raw.get("executable_source")
        if (
            not isinstance(cell_id, str)
            or not isinstance(language, str)
            or not isinstance(source, str)
        ):
            raise ValueError("runner broker cell values have invalid types")
        if language.casefold() != "python":
            raise ValueError("runner broker supports Python cells only")
        if len(source.encode("utf-8")) > _MAX_BODY_BYTES:
            raise ValueError("runner broker executable source exceeds configured limit")
        cell = CellExecutionRequest(
            CellId(cell_id),
            source,
            source,
            language,
            (),
            KernelDirective("runner-broker", "execute"),
        )
        return ExecutionAttemptId(attempt_raw), cell

    def begin_execution(self, execution_id: str) -> CancellationToken | None:
        with self._active_lock:
            if execution_id in self._active:
                return None
            token = CancellationToken()
            self._active[execution_id] = token
            return token

    def finish_execution(self, execution_id: str, token: CancellationToken) -> None:
        with self._active_lock:
            if self._active.get(execution_id) is token:
                del self._active[execution_id]

    def cancel_execution(self, execution_id: str) -> bool:
        with self._active_lock:
            token = self._active.get(execution_id)
        if token is None:
            return False
        token.cancel()
        return True

    async def execute(
        self,
        attempt_id: ExecutionAttemptId,
        cell: CellExecutionRequest,
        cancellation: CancellationToken,
    ) -> CellExecutionResult:
        executor = DockerContainerKernelExecutor(
            ContainerExecutorConfig(
                image=self.config.image,
                limits=self.config.limits,
                engine=self.config.engine,
            ),
            attempt_id,
            LocalExecutionEvidenceStore(self.config.evidence_root),
            engine_path=self.config.engine_path,
        )
        return await executor.execute(cell, cancellation)

    @staticmethod
    def result_payload(result: CellExecutionResult) -> dict[str, object]:
        return {
            "version": 1,
            "cell_id": str(result.cell_id),
            "state": result.state,
            "failure_code": result.failure_code,
            "evidence": [
                {
                    "kind": reference.kind,
                    "ref": reference.ref,
                    "digest_algorithm": reference.digest_algorithm,
                    "digest": reference.digest,
                    "media_type": reference.media_type,
                    "size_bytes": reference.size_bytes,
                }
                for reference in result.evidence
            ],
        }


__all__ = ("RunnerBrokerConfig", "RunnerBrokerServer")
