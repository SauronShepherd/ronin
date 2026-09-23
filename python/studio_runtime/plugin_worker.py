"""Portable plugin-worker/v1 request and failure semantics."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Coroutine, cast


class WorkerFailureKind(StrEnum):
    INVALID_PAYLOAD = "invalid_payload"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    CRASH = "crash"


@dataclass(frozen=True, slots=True)
class WorkerContract:
    api_version: str = "plugin-worker/v1"
    max_payload_bytes: int = 1_048_576
    timeout_seconds: float = 30.0

    def validate(self) -> None:
        if self.api_version != "plugin-worker/v1":
            raise ValueError("unsupported plugin worker API")
        if self.max_payload_bytes < 1:
            raise ValueError("worker payload limit must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("worker timeout must be positive")


@dataclass(frozen=True, slots=True)
class WorkerRequest:
    plugin_id: str
    operation_id: str
    payload: Mapping[str, Any]
    request_id: str

    def encoded_size(self) -> int:
        return len(
            json.dumps(
                self.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        )


@dataclass(frozen=True, slots=True)
class WorkerResponse:
    request_id: str
    payload: Any = None
    failure: WorkerFailureKind | None = None
    retryable: bool = False


def _failure(request_id: str, kind: WorkerFailureKind) -> WorkerResponse:
    return WorkerResponse(
        request_id,
        failure=kind,
        retryable=kind in {WorkerFailureKind.TIMEOUT, WorkerFailureKind.CRASH},
    )


async def execute_worker(
    request: WorkerRequest,
    handler: Callable[[Mapping[str, Any]], Any | Awaitable[Any]],
    *,
    contract: WorkerContract | None = None,
    cancellation: asyncio.Event | None = None,
) -> WorkerResponse:
    """Execute one bounded request with stable timeout/cancel/crash results."""
    if contract is None:
        contract = WorkerContract()
    contract.validate()
    if (
        not request.plugin_id.strip()
        or not request.operation_id.strip()
        or not request.request_id.strip()
    ):
        return _failure(request.request_id, WorkerFailureKind.INVALID_PAYLOAD)
    try:
        if request.encoded_size() > contract.max_payload_bytes:
            return _failure(request.request_id, WorkerFailureKind.INVALID_PAYLOAD)
    except (TypeError, ValueError, OverflowError):
        return _failure(request.request_id, WorkerFailureKind.INVALID_PAYLOAD)
    if cancellation is not None and cancellation.is_set():
        return _failure(request.request_id, WorkerFailureKind.CANCELLED)
    try:
        result = handler(request.payload)
        if not inspect.isawaitable(result):
            result = asyncio.sleep(0, result)
        task: asyncio.Task[Any] = asyncio.create_task(cast(Coroutine[Any, Any, Any], result))
        if cancellation is None:
            value = await asyncio.wait_for(task, contract.timeout_seconds)
        else:
            cancel_task = asyncio.create_task(cancellation.wait())
            done, _ = await asyncio.wait(
                {task, cancel_task},
                timeout=contract.timeout_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            cancel_task.cancel()
            if cancel_task in done and cancellation.is_set():
                task.cancel()
                return _failure(request.request_id, WorkerFailureKind.CANCELLED)
            if task not in done:
                task.cancel()
                return _failure(request.request_id, WorkerFailureKind.TIMEOUT)
            value = task.result()
        return WorkerResponse(request.request_id, payload=value)
    except TimeoutError:
        return _failure(request.request_id, WorkerFailureKind.TIMEOUT)
    except asyncio.CancelledError:
        return _failure(request.request_id, WorkerFailureKind.CANCELLED)
    except Exception:
        return _failure(request.request_id, WorkerFailureKind.CRASH)


__all__ = (
    "WorkerContract",
    "WorkerFailureKind",
    "WorkerRequest",
    "WorkerResponse",
    "execute_worker",
)
