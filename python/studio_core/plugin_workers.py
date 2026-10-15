"""Provider-neutral protocol contracts for isolated plugin workers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class WorkerProtocolError(ValueError):
    """Invalid worker handshake or message."""


class WorkerErrorCode(StrEnum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    PROTOCOL = "protocol"
    RESOURCE_LIMIT = "resource_limit"


@dataclass(frozen=True, slots=True)
class WorkerLimits:
    max_payload_bytes: int = 1024 * 1024
    heartbeat_seconds: int = 15
    execution_timeout_seconds: int = 3600

    def validate(self) -> None:
        if self.max_payload_bytes < 1 or self.heartbeat_seconds < 1:
            raise WorkerProtocolError("worker limits must be positive")
        if self.execution_timeout_seconds < self.heartbeat_seconds:
            raise WorkerProtocolError("execution timeout must cover heartbeat interval")


@dataclass(frozen=True, slots=True)
class WorkerHandshake:
    protocol: str
    plugin_id: str
    plugin_version: str
    capabilities: tuple[str, ...] = ()
    limits: WorkerLimits = WorkerLimits()

    def validate(self, *, expected_protocol: str = "1.0") -> None:
        if self.protocol != expected_protocol:
            raise WorkerProtocolError(
                f"unsupported worker protocol {self.protocol}; expected {expected_protocol}"
            )
        if not self.plugin_id or not self.plugin_version:
            raise WorkerProtocolError("worker handshake requires plugin identity")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise WorkerProtocolError("worker handshake has duplicate capabilities")
        self.limits.validate()


@dataclass(frozen=True, slots=True)
class WorkerMessage:
    kind: str
    request_id: str
    payload: dict[str, Any] = field(default_factory=dict)

    def validate(self, *, limits: WorkerLimits) -> None:
        if self.kind not in {"execute", "heartbeat", "cancel", "result", "error"}:
            raise WorkerProtocolError(f"unsupported worker message kind: {self.kind}")
        if not self.request_id or self.payload is None:
            raise WorkerProtocolError("worker message requires request_id and payload")
        import json

        encoded = json.dumps(self.payload, separators=(",", ":")).encode("utf-8")
        if len(encoded) > limits.max_payload_bytes:
            raise WorkerProtocolError("worker message exceeds payload limit")


@dataclass(frozen=True, slots=True)
class WorkerError:
    code: WorkerErrorCode
    message: str
    retryable: bool

    def validate(self) -> None:
        if not self.message or self.message != self.message.strip():
            raise WorkerProtocolError("worker error message must be trimmed")
        if self.retryable != (self.code is WorkerErrorCode.TRANSIENT):
            raise WorkerProtocolError("worker retryability does not match error code")


__all__ = (
    "WorkerError",
    "WorkerErrorCode",
    "WorkerHandshake",
    "WorkerLimits",
    "WorkerMessage",
    "WorkerProtocolError",
)
