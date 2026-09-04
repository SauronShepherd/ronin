from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from studio_core import ResolvedRuntimeSnapshot, RuntimeProfile, RuntimeProfileRef
from studio_kernel import (
    CancellationSignal,
    CancellationToken,
    CellExecutionRequest,
    CellExecutionResult,
    ExecutionAttemptId,
    ExecutionEvidenceReference,
    ExecutionReproducibilitySnapshot,
    ExecutorIsolation,
    JsonlExecutionEventSink,
    KernelDirective,
    KernelExecutionSession,
    NotebookExecutionRequest,
    RepositoryRevision,
    SessionPolicy,
    redact_sensitive_text,
)
from studio_notebook import CellId, Notebook, NotebookDocument


def _request() -> NotebookExecutionRequest:
    cell = CellExecutionRequest(
        CellId("cell-1"),
        "print('authored')",
        "print('executed')",
        "python",
        (),
        KernelDirective("test", "source.execute"),
    )
    return NotebookExecutionRequest(
        NotebookDocument(Notebook(), ()),
        ResolvedRuntimeSnapshot(
            None,
            RuntimeProfile(RuntimeProfileRef("local", "python")),
            "compatible",
            False,
            (),
            0,
        ),
        RepositoryRevision("a" * 40),
        ExecutionAttemptId("attempt-hardening"),
        ExecutionReproducibilitySnapshot(),
        (cell,),
    )


@dataclass
class _SuccessExecutor:
    isolation: ExecutorIsolation = ExecutorIsolation("container", True, True, True)

    def execute(
        self,
        cell: CellExecutionRequest,
        cancellation: CancellationSignal,
    ) -> CellExecutionResult:
        assert cancellation.is_cancelled is False
        return CellExecutionResult(cell.cell_id, "succeeded")


@dataclass
class _ExplodingExecutor:
    isolation: ExecutorIsolation = ExecutorIsolation("container", True, True, True)

    def execute(
        self,
        cell: CellExecutionRequest,
        cancellation: CancellationSignal,
    ) -> CellExecutionResult:
        raise RuntimeError("connection failed token=TOPSECRET")


def _events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_redaction_covers_prefixed_keys_bearer_jwt_provider_and_private_key() -> None:
    payload = (
        "AWS_SECRET_ACCESS_KEY=secret-value "
        "Bearer eyJhbGciOiJIUzI1NiJ9.abcdefghijk.signature "
        "ghp_abcdefghijklmnopqrstuvwxyz123456 "
        "-----BEGIN RSA PRIVATE KEY-----\nsecret\n-----END RSA PRIVATE KEY-----"
    )
    redacted = redact_sensitive_text(payload)
    assert "secret-value" not in redacted
    assert "eyJhbGciOiJIUzI1NiJ9" not in redacted
    assert "ghp_" not in redacted
    assert "BEGIN RSA PRIVATE KEY" not in redacted
    assert "[REDACTED]" in redacted


def test_evidence_reference_and_failure_code_are_redacted() -> None:
    reference = ExecutionEvidenceReference(
        "log", "https://user:password@example.test/log?token=secret-value"
    )
    result = CellExecutionResult(CellId("cell-1"), "failed", "token=secret-value")
    assert "password" not in reference.ref
    assert "secret-value" not in reference.ref
    assert result.failure_code == "token=[REDACTED]"


def test_kernel_session_is_single_use(tmp_path: Path) -> None:
    session = KernelExecutionSession(
        _request(),
        _SuccessExecutor(),
        SessionPolicy(),
        JsonlExecutionEventSink(tmp_path / "events.jsonl"),
        CancellationToken(),
    )
    assert session.run()[0].state == "succeeded"
    with pytest.raises(ValueError, match="already started"):
        session.run()


def test_executor_exception_is_normalized_but_redacted_detail_is_persisted(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    result = KernelExecutionSession(
        _request(),
        _ExplodingExecutor(),
        SessionPolicy(),
        JsonlExecutionEventSink(path),
        CancellationToken(),
    ).run()[0]

    assert result.failure_code == "kernel.executor.error"
    failed = next(event for event in _events(path) if event["kind"] == "cell.failed")
    message = str(failed["message"])
    assert "RuntimeError" in message
    assert "connection failed" in message
    assert "TOPSECRET" not in message
    assert "[REDACTED]" in message
