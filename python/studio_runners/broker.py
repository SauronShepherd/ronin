"""Structured remote executor for a constrained internal Docker runner broker."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import re
from dataclasses import dataclass, field
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.canonical_json import encode as encode_canonical_json
from studio_kernel import (
    CancellationSignal,
    CellExecutionRequest,
    CellExecutionResult,
    ExecutionAttemptId,
    ExecutionEvidenceReference,
    ExecutorIsolation,
)
from studio_kernel.contracts import EvidenceKind, ExecutionState
from studio_notebook import CellId

_IMMUTABLE_IMAGE = re.compile(r"^(?:[^\s]+@)?sha256:[0-9a-f]{64}$")
_EXECUTION_ID = re.compile(r"^exec-[0-9a-f]{32}$")
_DEFAULT_MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class BrokerProtocolError(RuntimeError):
    """Raised when a runner broker violates the structured protocol."""


class BrokerRequestError(RuntimeError):
    """Raised when the runner broker request cannot complete safely."""


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        del req, fp, code, msg, headers, newurl
        return


def _require_token(value: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError("runner broker token must be non-empty, trimmed, and single-line")
    return value


def _read_bounded(response, limit: int) -> bytes:  # noqa: ANN001
    declared = response.headers.get("Content-Length")
    if declared is not None:
        try:
            declared_size = int(declared)
        except ValueError as exc:
            raise BrokerProtocolError("runner broker returned invalid Content-Length") from exc
        if declared_size < 0 or declared_size > limit:
            raise BrokerProtocolError("runner broker response exceeded configured byte limit")
    data = response.read(limit + 1)
    if len(data) > limit:
        raise BrokerProtocolError("runner broker response exceeded configured byte limit")
    return data


def _object(payload: bytes) -> dict[str, object]:
    try:
        value = decode_canonical_json(payload)
    except (TypeError, ValueError) as exc:
        raise BrokerProtocolError("runner broker returned invalid canonical JSON") from exc
    if not isinstance(value, dict):
        raise BrokerProtocolError("runner broker response must be a JSON object")
    return cast(dict[str, object], value)


@dataclass(frozen=True, slots=True)
class BrokerExecutorConfig:
    base_url: str
    token: str
    expected_image: str
    allow_insecure_http: bool = False
    request_timeout_seconds: float = 330.0
    cancellation_poll_seconds: float = 0.05
    max_response_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
            raise ValueError("runner broker URL must be an absolute HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("runner broker URL must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("runner broker URL must not contain query or fragment")
        if parsed.path not in {"", "/"}:
            raise ValueError("runner broker URL must not contain a path")
        if parsed.scheme == "http" and not self.allow_insecure_http:
            raise ValueError("plaintext runner broker HTTP requires explicit opt-in")
        _require_token(self.token)
        if not _IMMUTABLE_IMAGE.fullmatch(self.expected_image):
            raise ValueError("runner broker expected image must be an immutable sha256 identity")
        if self.request_timeout_seconds <= 0 or self.request_timeout_seconds > 3600:
            raise ValueError("runner broker request timeout must be in (0, 3600]")
        if self.cancellation_poll_seconds <= 0 or self.cancellation_poll_seconds > 1:
            raise ValueError("runner broker cancellation poll interval must be in (0, 1]")
        if self.max_response_bytes < 1 or self.max_response_bytes > 64 * 1024 * 1024:
            raise ValueError("runner broker response limit must be between 1 byte and 64 MiB")


@dataclass(frozen=True, slots=True)
class BrokerClient:
    config: BrokerExecutorConfig
    _opener: object = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_opener", build_opener(_RejectRedirects()))

    def _request(self, method: str, path: str, payload: object | None = None) -> dict[str, object]:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("runner broker path must be origin-relative")
        data = None if payload is None else encode_canonical_json(payload)
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.config.token}",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(data))
        request = Request(  # noqa: S310
            self.config.base_url.rstrip("/") + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with self._opener.open(  # type: ignore[attr-defined]  # noqa: S310
                request,
                timeout=self.config.request_timeout_seconds,
            ) as response:
                body = _read_bounded(response, self.config.max_response_bytes)
        except HTTPError as exc:
            try:
                body = _read_bounded(exc, min(self.config.max_response_bytes, 64 * 1024))
                error = _object(body)
                code = error.get("code")
                detail = code if isinstance(code, str) else "request_failed"
            except (BrokerProtocolError, OSError):
                detail = "request_failed"
            raise BrokerRequestError(
                f"runner broker request failed ({exc.code}, {detail})"
            ) from exc
        except (OSError, URLError) as exc:
            raise BrokerRequestError("runner broker request failed") from exc
        return _object(body)

    def runtime_image(self) -> str:
        payload = self._request("GET", "/v1/runtime")
        if set(payload) != {"image", "version"} or payload.get("version") != 1:
            raise BrokerProtocolError("runner broker runtime response has invalid fields")
        image = payload.get("image")
        if not isinstance(image, str) or not _IMMUTABLE_IMAGE.fullmatch(image):
            raise BrokerProtocolError("runner broker runtime image is invalid")
        if image != self.config.expected_image:
            raise BrokerProtocolError(
                "runner broker runtime image does not match expected identity"
            )
        return image

    def execute(
        self,
        execution_id: str,
        attempt_id: ExecutionAttemptId,
        cell: CellExecutionRequest,
    ) -> CellExecutionResult:
        if not _EXECUTION_ID.fullmatch(execution_id):
            raise ValueError("runner broker execution id is invalid")
        payload = self._request(
            "POST",
            f"/v1/executions/{quote(execution_id, safe='')}",
            {
                "version": 1,
                "attempt_id": str(attempt_id),
                "cell": {
                    "cell_id": str(cell.cell_id),
                    "language": cell.language,
                    "executable_source": cell.executable_source,
                },
            },
        )
        if set(payload) != {"cell_id", "state", "failure_code", "evidence", "version"}:
            raise BrokerProtocolError("runner broker execution response has invalid fields")
        if payload.get("version") != 1:
            raise BrokerProtocolError("runner broker execution response version is unsupported")
        cell_id = payload.get("cell_id")
        state = payload.get("state")
        failure_code = payload.get("failure_code")
        raw_evidence = payload.get("evidence")
        if cell_id != str(cell.cell_id):
            raise BrokerProtocolError("runner broker returned a different cell id")
        if state not in {"succeeded", "failed", "cancelled"}:
            raise BrokerProtocolError("runner broker returned an invalid execution state")
        if failure_code is not None and not isinstance(failure_code, str):
            raise BrokerProtocolError("runner broker failure code is invalid")
        if not isinstance(raw_evidence, list):
            raise BrokerProtocolError("runner broker evidence collection is invalid")
        evidence: list[ExecutionEvidenceReference] = []
        for item in raw_evidence:
            if not isinstance(item, dict) or set(item) != {
                "kind",
                "ref",
                "digest_algorithm",
                "digest",
                "media_type",
                "size_bytes",
            }:
                raise BrokerProtocolError("runner broker evidence item has invalid fields")
            evidence.append(
                ExecutionEvidenceReference(
                    cast(EvidenceKind, item["kind"]),
                    cast(str, item["ref"]),
                    cast(str | None, item["digest_algorithm"]),
                    cast(str | None, item["digest"]),
                    cast(str | None, item["media_type"]),
                    cast(int | None, item["size_bytes"]),
                )
            )
        return CellExecutionResult(
            CellId(cast(str, cell_id)),
            cast(ExecutionState, state),
            cast(str | None, failure_code),
            tuple(evidence),
        )

    def cancel(self, execution_id: str) -> None:
        if not _EXECUTION_ID.fullmatch(execution_id):
            raise ValueError("runner broker execution id is invalid")
        payload = self._request("DELETE", f"/v1/executions/{quote(execution_id, safe='')}")
        if set(payload) != {"cancelled", "version"} or payload.get("version") != 1:
            raise BrokerProtocolError("runner broker cancellation response has invalid fields")
        if payload.get("cancelled") is not True:
            raise BrokerProtocolError("runner broker did not acknowledge cancellation")


@dataclass(slots=True)
class BrokerContainerKernelExecutor:
    """Kernel executor that can request only one constrained broker cell execution."""

    config: BrokerExecutorConfig
    attempt_id: ExecutionAttemptId
    client: BrokerClient | None = None

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = BrokerClient(self.config)

    @property
    def isolation(self) -> ExecutorIsolation:
        return ExecutorIsolation(
            "container",
            True,
            True,
            True,
            "tested",
            "ronin/docker-isolation",
            "1",
            self.config.expected_image,
            "qualification://docker/real-adversarial-v1",
        )

    def _execution_id(self, cell: CellExecutionRequest) -> str:
        identity = f"{self.attempt_id}:{cell.cell_id}".encode()
        return "exec-" + hashlib.sha256(identity).hexdigest()[:32]

    async def execute(
        self,
        cell: CellExecutionRequest,
        cancellation: CancellationSignal,
    ) -> CellExecutionResult:
        if cancellation.is_cancelled:
            return CellExecutionResult(cell.cell_id, "cancelled")
        client = cast(BrokerClient, self.client)
        await asyncio.to_thread(client.runtime_image)
        execution_id = self._execution_id(cell)
        task = asyncio.create_task(
            asyncio.to_thread(client.execute, execution_id, self.attempt_id, cell)
        )
        cancellation_sent = False
        try:
            while not task.done():
                if cancellation.is_cancelled and not cancellation_sent:
                    cancellation_sent = True
                    with contextlib.suppress(BrokerRequestError):
                        await asyncio.to_thread(client.cancel, execution_id)
                await asyncio.sleep(self.config.cancellation_poll_seconds)
            return await task
        except asyncio.CancelledError:
            if not task.done():
                with contextlib.suppress(BrokerRequestError):
                    await asyncio.to_thread(client.cancel, execution_id)
            task.cancel()
            raise


__all__ = (
    "BrokerClient",
    "BrokerContainerKernelExecutor",
    "BrokerExecutorConfig",
    "BrokerProtocolError",
    "BrokerRequestError",
)
