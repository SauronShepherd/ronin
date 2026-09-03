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
    ExecutionEvent,
    ExecutionEventId,
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


def _runtime() -> ResolvedRuntimeSnapshot:
    return ResolvedRuntimeSnapshot(
        None,
        RuntimeProfile(RuntimeProfileRef("local", "python")),
        "compatible",
        False,
        (),
        0,
    )


def _cell(
    value: str,
    *,
    permissions: tuple[str, ...] = (),
) -> CellExecutionRequest:
    cell_id = CellId(value)
    return CellExecutionRequest(
        cell_id,
        "print('authored')",
        "print('executed')",
        "python",
        (),
        KernelDirective("test", "source.execute", required_permissions=permissions),
    )


def _request(*cells: CellExecutionRequest) -> NotebookExecutionRequest:
    return NotebookExecutionRequest(
        NotebookDocument(Notebook(), ()),
        _runtime(),
        RepositoryRevision("a" * 40),
        ExecutionAttemptId("attempt-1"),
        ExecutionReproducibilitySnapshot(),
        cells,
    )


@dataclass
class _Executor:
    results: list[CellExecutionResult]
    isolation: ExecutorIsolation = ExecutorIsolation("container", True, True, True)
    cancel_token: CancellationToken | None = None
    wrong_cell: bool = False

    def execute(
        self,
        cell: CellExecutionRequest,
        cancellation: CancellationSignal,
    ) -> CellExecutionResult:
        if self.cancel_token is not None:
            self.cancel_token.cancel()
        result = self.results.pop(0)
        assert cell.cell_id == result.cell_id
        if self.wrong_cell:
            return CellExecutionResult(CellId("wrong"), result.state, result.failure_code)
        assert cancellation.is_cancelled is (self.cancel_token is not None)
        return result


def _read_events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_redaction_covers_named_secrets_bearer_tokens_and_uri_credentials() -> None:
    redacted = redact_sensitive_text(
        "token=abc password:'def' Authorization: Bearer ghi https://user:pw@example.test/path"
    )
    assert "abc" not in redacted
    assert "def" not in redacted
    assert "ghi" not in redacted
    assert "pw" not in redacted
    assert redacted.count("[REDACTED]") == 4
    assert redact_sensitive_text(42) == "42"


def test_executor_isolation_and_session_policy_fail_closed() -> None:
    with pytest.raises(ValueError, match="unsupported executor isolation"):
        ExecutorIsolation("vm", True, True, True)  # type: ignore[arg-type]

    policy = SessionPolicy(("network.egress",), ("container",))
    assert policy.granted_permissions == ("network.egress",)
    assert policy.allowed_isolation_modes == ("container",)
    assert policy.missing_permissions(_cell("cell", permissions=("network.egress",))) == ()
    assert policy.missing_permissions(_cell("cell", permissions=("secrets.read",))) == (
        "secrets.read",
    )

    with pytest.raises(ValueError, match="permissions must be unique"):
        SessionPolicy(("same", "same"))
    with pytest.raises(ValueError, match="session permission"):
        SessionPolicy((" bad ",))
    with pytest.raises(ValueError, match="at least one isolation"):
        SessionPolicy(allowed_isolation_modes=())
    with pytest.raises(ValueError, match="allowed isolation modes must be unique"):
        SessionPolicy(allowed_isolation_modes=("container", "container"))
    with pytest.raises(ValueError, match="unsupported allowed isolation"):
        SessionPolicy(allowed_isolation_modes=("vm",))  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="mode is not allowed"):
        policy.validate_isolation(ExecutorIsolation("process", True, True, True))
    with pytest.raises(ValueError, match="dedicated identity"):
        policy.validate_isolation(ExecutorIsolation("container", False, True, True))
    with pytest.raises(ValueError, match="network isolation"):
        policy.validate_isolation(ExecutorIsolation("container", True, False, True))
    with pytest.raises(ValueError, match="filesystem isolation"):
        policy.validate_isolation(ExecutorIsolation("container", True, True, False))

    relaxed = SessionPolicy(
        allowed_isolation_modes=("process",),
        require_dedicated_identity=False,
        require_network_isolation=False,
        require_filesystem_isolation=False,
    )
    relaxed.validate_isolation(ExecutorIsolation("process", False, False, False))


def test_cancellation_token_is_thread_safe_signal() -> None:
    token = CancellationToken()
    assert token.is_cancelled is False
    token.cancel()
    assert token.is_cancelled is True


def test_execution_event_redacts_and_serializes_canonically() -> None:
    event = ExecutionEvent(
        ExecutionEventId(ExecutionAttemptId("attempt-1"), 3),
        "cell.failed",
        CellId("cell-1"),
        "password=hunter2",
    )
    assert event.message == "password=[REDACTED]"
    assert json.loads(event.to_json()) == {
        "attempt_id": "attempt-1",
        "cell_id": "cell-1",
        "kind": "cell.failed",
        "message": "password=[REDACTED]",
        "sequence": 3,
    }
    with pytest.raises(ValueError, match="unsupported execution event"):
        ExecutionEvent(ExecutionEventId(ExecutionAttemptId("attempt-1"), 0), "bad")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must not contain NUL"):
        ExecutionEvent(
            ExecutionEventId(ExecutionAttemptId("attempt-1"), 0),
            "session.failed",
            message="bad\x00message",
        )


def test_jsonl_sink_persists_fsynced_contiguous_single_attempt_events(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "events.jsonl"
    sink = JsonlExecutionEventSink(path)
    attempt = ExecutionAttemptId("attempt-1")
    sink.append(ExecutionEvent(ExecutionEventId(attempt, 0), "session.started"))
    sink.append(ExecutionEvent(ExecutionEventId(attempt, 1), "session.completed"))
    assert [event["sequence"] for event in _read_events(path)] == [0, 1]

    with pytest.raises(ValueError, match="contiguous sequence"):
        sink.append(ExecutionEvent(ExecutionEventId(attempt, 3), "session.completed"))
    with pytest.raises(ValueError, match="only one execution attempt"):
        sink.append(
            ExecutionEvent(
                ExecutionEventId(ExecutionAttemptId("attempt-2"), 2),
                "session.completed",
            )
        )


def test_session_success_emits_ordered_durable_events(tmp_path: Path) -> None:
    first = _cell("cell-1")
    second = _cell("cell-2")
    request = _request(first, second)
    executor = _Executor(
        [
            CellExecutionResult(first.cell_id, "succeeded"),
            CellExecutionResult(second.cell_id, "succeeded"),
        ]
    )
    path = tmp_path / "events.jsonl"
    results = KernelExecutionSession(
        request,
        executor,
        SessionPolicy(),
        JsonlExecutionEventSink(path),
        CancellationToken(),
    ).run()

    assert [result.state for result in results] == ["succeeded", "succeeded"]
    assert [event["kind"] for event in _read_events(path)] == [
        "session.started",
        "cell.started",
        "cell.succeeded",
        "cell.started",
        "cell.succeeded",
        "session.completed",
    ]


def test_session_denies_missing_permissions_before_executor_side_effects(tmp_path: Path) -> None:
    cell = _cell("cell-1", permissions=("network.egress",))
    executor = _Executor([CellExecutionResult(cell.cell_id, "succeeded")])
    path = tmp_path / "events.jsonl"
    results = KernelExecutionSession(
        _request(cell),
        executor,
        SessionPolicy(),
        JsonlExecutionEventSink(path),
        CancellationToken(),
    ).run()

    assert results == (CellExecutionResult(cell.cell_id, "failed", "kernel.permission.denied"),)
    assert len(executor.results) == 1
    assert [event["kind"] for event in _read_events(path)] == [
        "session.started",
        "permission.denied",
        "cell.failed",
        "session.failed",
    ]


def test_session_stops_on_failure_and_cancelled_result(tmp_path: Path) -> None:
    failed_cell = _cell("failed")
    failed_path = tmp_path / "failed.jsonl"
    failed = KernelExecutionSession(
        _request(failed_cell),
        _Executor([CellExecutionResult(failed_cell.cell_id, "failed", "kernel.failure")]),
        SessionPolicy(),
        JsonlExecutionEventSink(failed_path),
        CancellationToken(),
    ).run()
    assert failed[0].state == "failed"
    assert [event["kind"] for event in _read_events(failed_path)][-2:] == [
        "cell.failed",
        "session.failed",
    ]

    cancelled_cell = _cell("cancelled")
    cancelled_path = tmp_path / "cancelled.jsonl"
    cancelled = KernelExecutionSession(
        _request(cancelled_cell),
        _Executor([CellExecutionResult(cancelled_cell.cell_id, "cancelled")]),
        SessionPolicy(),
        JsonlExecutionEventSink(cancelled_path),
        CancellationToken(),
    ).run()
    assert cancelled[0].state == "cancelled"
    assert [event["kind"] for event in _read_events(cancelled_path)][-2:] == [
        "cell.cancelled",
        "session.cancelled",
    ]


def test_session_honors_cancellation_before_and_between_cells(tmp_path: Path) -> None:
    cell = _cell("cell-1")
    already_cancelled = CancellationToken()
    already_cancelled.cancel()
    first_path = tmp_path / "before.jsonl"
    assert (
        KernelExecutionSession(
            _request(cell),
            _Executor([CellExecutionResult(cell.cell_id, "succeeded")]),
            SessionPolicy(),
            JsonlExecutionEventSink(first_path),
            already_cancelled,
        ).run()
        == ()
    )
    assert [event["kind"] for event in _read_events(first_path)] == [
        "session.started",
        "session.cancelled",
    ]

    first = _cell("first")
    second = _cell("second")
    token = CancellationToken()
    between_path = tmp_path / "between.jsonl"
    results = KernelExecutionSession(
        _request(first, second),
        _Executor(
            [
                CellExecutionResult(first.cell_id, "succeeded"),
                CellExecutionResult(second.cell_id, "succeeded"),
            ],
            cancel_token=token,
        ),
        SessionPolicy(),
        JsonlExecutionEventSink(between_path),
        token,
    ).run()
    assert len(results) == 1
    assert [event["kind"] for event in _read_events(between_path)][-1] == "session.cancelled"


def test_session_rejects_executor_identity_drift_and_bad_isolation(tmp_path: Path) -> None:
    cell = _cell("cell-1")
    with pytest.raises(ValueError, match="preserve cell identity"):
        KernelExecutionSession(
            _request(cell),
            _Executor([CellExecutionResult(cell.cell_id, "succeeded")], wrong_cell=True),
            SessionPolicy(),
            JsonlExecutionEventSink(tmp_path / "identity.jsonl"),
            CancellationToken(),
        ).run()

    with pytest.raises(ValueError, match="network isolation"):
        KernelExecutionSession(
            _request(cell),
            _Executor(
                [CellExecutionResult(cell.cell_id, "succeeded")],
                isolation=ExecutorIsolation("container", True, False, True),
            ),
            SessionPolicy(),
            JsonlExecutionEventSink(tmp_path / "isolation.jsonl"),
            CancellationToken(),
        ).run()
