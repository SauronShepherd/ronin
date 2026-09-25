from __future__ import annotations

import pytest

from studio_core.plugin_workers import (
    WorkerError,
    WorkerErrorCode,
    WorkerHandshake,
    WorkerLimits,
    WorkerMessage,
    WorkerProtocolError,
)


def test_worker_handshake_and_message_validate() -> None:
    handshake = WorkerHandshake("1.0", "com.example.worker", "1.0.0")
    handshake.validate()
    message = WorkerMessage("execute", "request-1", {"job": "example"})

    message.validate(limits=handshake.limits)


def test_worker_rejects_protocol_and_payload_violations() -> None:
    with pytest.raises(WorkerProtocolError, match="unsupported worker protocol"):
        WorkerHandshake("2.0", "example", "1.0").validate()
    with pytest.raises(WorkerProtocolError, match="exceeds payload"):
        WorkerMessage("execute", "request-1", {"data": "x" * 20}).validate(
            limits=WorkerLimits(max_payload_bytes=10)
        )


def test_worker_error_taxonomy_controls_retry() -> None:
    transient = WorkerError(WorkerErrorCode.TRANSIENT, "temporary provider failure", True)
    transient.validate()
    with pytest.raises(WorkerProtocolError, match="retryability"):
        WorkerError(WorkerErrorCode.PERMANENT, "permanent failure", True).validate()
