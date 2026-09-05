"""Fail-closed kernel execution-session controls and durable event emission."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, TypeAlias, cast

from studio_notebook import CellId

from .contracts import CellExecutionRequest, CellExecutionResult, NotebookExecutionRequest
from .redaction import redact_sensitive_text
from .reproducibility import ExecutionAttemptId, ExecutionEventId

IsolationMode: TypeAlias = Literal["process", "container", "kubernetes"]
IsolationQualification: TypeAlias = Literal["declared", "tested", "qualified"]
ExecutionEventKind: TypeAlias = Literal[
    "session.started",
    "session.completed",
    "session.cancelled",
    "session.failed",
    "cell.started",
    "cell.succeeded",
    "cell.failed",
    "cell.cancelled",
    "permission.denied",
]

_EVENT_LEDGER_KEYS = frozenset({"attempt_id", "sequence", "kind", "cell_id", "message"})
_QUALIFICATION_RANK: dict[IsolationQualification, int] = {
    "declared": 0,
    "tested": 1,
    "qualified": 2,
}


def _require_text(value: str, name: str) -> None:
    if not value or value.strip() != value or "\n" in value or "\r" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")


@dataclass(frozen=True, slots=True)
class ExecutorIsolation:
    """Versioned isolation claim declared or evidenced by an executor adapter."""

    mode: IsolationMode
    dedicated_identity: bool
    network_isolated: bool
    filesystem_isolated: bool
    qualification_status: IsolationQualification = "declared"
    qualification_scheme: str | None = None
    qualification_version: str | None = None
    runtime_identity: str | None = None
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"process", "container", "kubernetes"}:
            raise ValueError("unsupported executor isolation mode")
        if self.qualification_status not in _QUALIFICATION_RANK:
            raise ValueError("unsupported isolation qualification status")
        metadata = (
            self.qualification_scheme,
            self.qualification_version,
            self.runtime_identity,
            self.evidence_ref,
        )
        if self.qualification_status == "declared":
            if any(value is not None for value in metadata):
                raise ValueError("declared isolation claims must not carry qualification evidence")
            return
        if any(value is None for value in metadata):
            raise ValueError(
                "tested/qualified isolation claims require complete qualification evidence"
            )
        for value, name in zip(
            cast(tuple[str, str, str, str], metadata),
            (
                "qualification scheme",
                "qualification version",
                "runtime identity",
                "evidence reference",
            ),
            strict=True,
        ):
            _require_text(value, name)


@dataclass(frozen=True, slots=True)
class SessionPolicy:
    """Minimum controls required before an executor may run notebook code."""

    granted_permissions: tuple[str, ...] = ()
    allowed_isolation_modes: tuple[IsolationMode, ...] = ("container", "kubernetes")
    require_dedicated_identity: bool = True
    require_network_isolation: bool = True
    require_filesystem_isolation: bool = True
    minimum_isolation_qualification: IsolationQualification = "declared"

    def __post_init__(self) -> None:
        permissions = tuple(sorted(self.granted_permissions))
        if len(set(permissions)) != len(permissions):
            raise ValueError("session permissions must be unique")
        for permission in permissions:
            _require_text(permission, "session permission")
        modes = tuple(sorted(self.allowed_isolation_modes))
        if not modes:
            raise ValueError("session policy must allow at least one isolation mode")
        if len(set(modes)) != len(modes):
            raise ValueError("allowed isolation modes must be unique")
        if any(mode not in {"process", "container", "kubernetes"} for mode in modes):
            raise ValueError("unsupported allowed isolation mode")
        if self.minimum_isolation_qualification not in _QUALIFICATION_RANK:
            raise ValueError("unsupported minimum isolation qualification")
        object.__setattr__(self, "granted_permissions", permissions)
        object.__setattr__(self, "allowed_isolation_modes", modes)

    def missing_permissions(self, cell: CellExecutionRequest) -> tuple[str, ...]:
        granted = set(self.granted_permissions)
        return tuple(
            permission
            for permission in cell.directive.required_permissions
            if permission not in granted
        )

    def validate_isolation(self, isolation: ExecutorIsolation) -> None:
        if isolation.mode not in self.allowed_isolation_modes:
            raise ValueError("executor isolation mode is not allowed by session policy")
        if self.require_dedicated_identity and not isolation.dedicated_identity:
            raise ValueError("executor must use a dedicated identity")
        if self.require_network_isolation and not isolation.network_isolated:
            raise ValueError("executor must provide network isolation")
        if self.require_filesystem_isolation and not isolation.filesystem_isolated:
            raise ValueError("executor must provide filesystem isolation")
        if (
            _QUALIFICATION_RANK[isolation.qualification_status]
            < _QUALIFICATION_RANK[self.minimum_isolation_qualification]
        ):
            raise ValueError("executor isolation qualification is below session policy minimum")


class CancellationSignal(Protocol):
    @property
    def is_cancelled(self) -> bool: ...


@dataclass(slots=True)
class CancellationToken:
    """Thread-safe cancellation signal shared with a concrete executor adapter."""

    _event: threading.Event = field(default_factory=threading.Event, init=False, repr=False)

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    """Ordered redacted operational evidence for one execution attempt."""

    event_id: ExecutionEventId
    kind: ExecutionEventKind
    cell_id: CellId | None = None
    message: str = ""

    def __post_init__(self) -> None:
        if self.kind not in {
            "session.started",
            "session.completed",
            "session.cancelled",
            "session.failed",
            "cell.started",
            "cell.succeeded",
            "cell.failed",
            "cell.cancelled",
            "permission.denied",
        }:
            raise ValueError("unsupported execution event kind")
        if "\x00" in self.message:
            raise ValueError("execution event message must not contain NUL")
        object.__setattr__(self, "message", redact_sensitive_text(self.message))

    def to_json(self) -> str:
        payload = {
            "attempt_id": str(self.event_id.attempt_id),
            "sequence": self.event_id.sequence,
            "kind": self.kind,
            "cell_id": str(self.cell_id) if self.cell_id is not None else None,
            "message": self.message,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class ExecutionEventSink(Protocol):
    def append(self, event: ExecutionEvent) -> None: ...


def _decode_ledger_identity(line: str) -> tuple[ExecutionAttemptId, int]:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError("existing event ledger contains invalid JSON") from exc
    if not isinstance(payload, dict) or set(payload) != _EVENT_LEDGER_KEYS:
        raise ValueError("existing event ledger has invalid event shape")
    attempt_id = payload["attempt_id"]
    sequence = payload["sequence"]
    kind = payload["kind"]
    cell_id = payload["cell_id"]
    message = payload["message"]
    if not isinstance(attempt_id, str):
        raise ValueError("existing event ledger has invalid attempt identity")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise ValueError("existing event ledger has invalid event sequence")
    if not isinstance(kind, str):
        raise ValueError("existing event ledger has invalid event kind")
    if cell_id is not None and not isinstance(cell_id, str):
        raise ValueError("existing event ledger has invalid cell identity")
    if not isinstance(message, str):
        raise ValueError("existing event ledger has invalid event message")
    try:
        event = ExecutionEvent(
            ExecutionEventId(ExecutionAttemptId(attempt_id), sequence),
            cast(ExecutionEventKind, kind),
            CellId(cell_id) if cell_id is not None else None,
            message,
        )
    except ValueError as exc:
        raise ValueError("existing event ledger contains invalid event semantics") from exc
    return event.event_id.attempt_id, event.event_id.sequence


@dataclass(slots=True)
class JsonlExecutionEventSink:
    """Restart-safe single-writer JSONL sink with contiguous event identities."""

    path: Path
    _attempt_id: ExecutionAttemptId | None = field(default=None, init=False, repr=False)
    _next_sequence: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.path.exists():
            return
        raw = self.path.read_text(encoding="utf-8")
        if not raw:
            return
        if not raw.endswith("\n"):
            raise ValueError("existing event ledger ends with a partial event")
        attempt_id: ExecutionAttemptId | None = None
        next_sequence = 0
        for line in raw.splitlines():
            current_attempt, sequence = _decode_ledger_identity(line)
            if attempt_id is None:
                attempt_id = current_attempt
            elif current_attempt != attempt_id:
                raise ValueError("existing event ledger mixes execution attempts")
            if sequence != next_sequence:
                raise ValueError("existing event ledger sequence is not contiguous")
            next_sequence += 1
        self._attempt_id = attempt_id
        self._next_sequence = next_sequence

    def append(self, event: ExecutionEvent) -> None:
        if self._attempt_id is None:
            self._attempt_id = event.event_id.attempt_id
        elif event.event_id.attempt_id != self._attempt_id:
            raise ValueError("event sink may persist only one execution attempt")
        if event.event_id.sequence != self._next_sequence:
            raise ValueError("execution events must be appended in contiguous sequence order")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(event.to_json())
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._next_sequence += 1


class KernelCellExecutor(Protocol):
    """Awaitable adapter boundary that performs one prepared cell side effect."""

    @property
    def isolation(self) -> ExecutorIsolation: ...

    async def execute(
        self,
        cell: CellExecutionRequest,
        cancellation: CancellationSignal,
    ) -> CellExecutionResult: ...


@dataclass(slots=True)
class KernelExecutionSession:
    """Run prepared cells asynchronously behind policy and durable evidence controls."""

    request: NotebookExecutionRequest
    executor: KernelCellExecutor
    policy: SessionPolicy
    event_sink: ExecutionEventSink
    cancellation: CancellationSignal
    _next_sequence: int = field(default=0, init=False, repr=False)
    _started: bool = field(default=False, init=False, repr=False)
    _start_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def _emit(
        self,
        kind: ExecutionEventKind,
        *,
        cell_id: CellId | None = None,
        message: str = "",
    ) -> None:
        event = ExecutionEvent(
            ExecutionEventId(self.request.attempt_id, self._next_sequence),
            kind,
            cell_id,
            message,
        )
        self.event_sink.append(event)
        self._next_sequence += 1

    async def run(self) -> tuple[CellExecutionResult, ...]:
        self.policy.validate_isolation(self.executor.isolation)
        with self._start_lock:
            if self._started:
                raise ValueError("session already started")
            self._started = True
        self._emit("session.started")
        results: list[CellExecutionResult] = []
        for cell in self.request.cells:
            if self.cancellation.is_cancelled:
                self._emit("session.cancelled")
                return tuple(results)
            missing_permissions = self.policy.missing_permissions(cell)
            if missing_permissions:
                self._emit(
                    "permission.denied",
                    cell_id=cell.cell_id,
                    message="missing permissions: " + ",".join(missing_permissions),
                )
                result = CellExecutionResult(
                    cell.cell_id,
                    "failed",
                    "kernel.permission.denied",
                )
                results.append(result)
                self._emit("cell.failed", cell_id=cell.cell_id, message=result.failure_code or "")
                self._emit("session.failed")
                return tuple(results)
            self._emit("cell.started", cell_id=cell.cell_id)
            failure_detail = ""
            try:
                result = await self.executor.execute(cell, self.cancellation)
            except asyncio.CancelledError:
                self._emit("cell.cancelled", cell_id=cell.cell_id)
                self._emit("session.cancelled")
                raise
            except Exception as exc:
                failure_detail = type(exc).__name__
                result = CellExecutionResult(cell.cell_id, "failed", "kernel.executor.error")
            if result.cell_id != cell.cell_id:
                raise ValueError("kernel executor must preserve cell identity")
            results.append(result)
            if result.state == "succeeded":
                self._emit("cell.succeeded", cell_id=cell.cell_id)
                continue
            if result.state == "cancelled":
                self._emit("cell.cancelled", cell_id=cell.cell_id)
                self._emit("session.cancelled")
                return tuple(results)
            message = result.failure_code or ""
            if failure_detail:
                message = f"{message}; executor exception: {failure_detail}"
            self._emit("cell.failed", cell_id=cell.cell_id, message=message)
            self._emit("session.failed")
            return tuple(results)
        self._emit("session.completed")
        return tuple(results)
