"""Fail-closed kernel execution-session controls and durable event emission."""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, TypeAlias

from studio_notebook import CellId

from .contracts import CellExecutionRequest, CellExecutionResult, NotebookExecutionRequest
from .reproducibility import ExecutionAttemptId, ExecutionEventId

IsolationMode: TypeAlias = Literal["process", "container", "kubernetes"]
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

_SECRET_PATTERN = re.compile(
    r"(?ix)(authorization\s*[:=]\s*bearer\s+|"
    r"[\"']?(?:token|secret|password|passwd|api[_-]?key)[\"']?\s*[:=]\s*[\"']?)"
    r"([^\s,\"';}]+)"
)
_URI_CREDENTIAL_PATTERN = re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^\s:/@]+:)([^\s/@]+)(@)")


def _require_text(value: str, name: str) -> None:
    if not value or value.strip() != value or "\n" in value or "\r" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")


def redact_sensitive_text(value: object) -> str:
    """Redact common credentials before operational text reaches durable storage."""
    text = str(value)
    text = _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}[REDACTED]", text)
    return _URI_CREDENTIAL_PATTERN.sub(
        lambda match: f"{match.group(1)}[REDACTED]{match.group(3)}",
        text,
    )


@dataclass(frozen=True, slots=True)
class ExecutorIsolation:
    """Isolation facts declared by a concrete executor adapter."""

    mode: IsolationMode
    dedicated_identity: bool
    network_isolated: bool
    filesystem_isolated: bool

    def __post_init__(self) -> None:
        if self.mode not in {"process", "container", "kubernetes"}:
            raise ValueError("unsupported executor isolation mode")


@dataclass(frozen=True, slots=True)
class SessionPolicy:
    """Minimum controls required before an executor may run notebook code."""

    granted_permissions: tuple[str, ...] = ()
    allowed_isolation_modes: tuple[IsolationMode, ...] = ("container", "kubernetes")
    require_dedicated_identity: bool = True
    require_network_isolation: bool = True
    require_filesystem_isolation: bool = True

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


@dataclass(slots=True)
class JsonlExecutionEventSink:
    """Append-only fsynced JSONL sink that rejects out-of-order event identities."""

    path: Path
    _attempt_id: ExecutionAttemptId | None = field(default=None, init=False, repr=False)
    _next_sequence: int = field(default=0, init=False, repr=False)

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
    """Concrete adapter boundary that performs one prepared cell side effect."""

    @property
    def isolation(self) -> ExecutorIsolation: ...

    def execute(
        self,
        cell: CellExecutionRequest,
        cancellation: CancellationSignal,
    ) -> CellExecutionResult: ...


@dataclass(slots=True)
class KernelExecutionSession:
    """Run prepared cells behind policy, cancellation, redaction and durable events."""

    request: NotebookExecutionRequest
    executor: KernelCellExecutor
    policy: SessionPolicy
    event_sink: ExecutionEventSink
    cancellation: CancellationSignal
    _next_sequence: int = field(default=0, init=False, repr=False)

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

    def run(self) -> tuple[CellExecutionResult, ...]:
        self.policy.validate_isolation(self.executor.isolation)
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
            try:
                result = self.executor.execute(cell, self.cancellation)
            except Exception:
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

            self._emit("cell.failed", cell_id=cell.cell_id, message=result.failure_code or "")
            self._emit("session.failed")
            return tuple(results)

        self._emit("session.completed")
        return tuple(results)
