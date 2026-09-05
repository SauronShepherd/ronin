from __future__ import annotations

import asyncio
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
    ExecutionReproducibilitySnapshot,
    ExecutorIsolation,
    JsonlExecutionEventSink,
    KernelDirective,
    KernelExecutionSession,
    NotebookExecutionRequest,
    RepositoryRevision,
    SessionPolicy,
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


def _cell() -> CellExecutionRequest:
    return CellExecutionRequest(
        CellId("cell-1"),
        "print('authored')",
        "print('executed')",
        "python",
        (),
        KernelDirective("test", "source.execute"),
    )


def _request(cell: CellExecutionRequest) -> NotebookExecutionRequest:
    return NotebookExecutionRequest(
        NotebookDocument(Notebook(), ()),
        _runtime(),
        RepositoryRevision("a" * 40),
        ExecutionAttemptId("attempt-cancelled"),
        ExecutionReproducibilitySnapshot(),
        (cell,),
    )


@dataclass
class _TaskCancelledExecutor:
    isolation: ExecutorIsolation = ExecutorIsolation("container", True, True, True)

    async def execute(
        self,
        cell: CellExecutionRequest,
        cancellation: CancellationSignal,
    ) -> CellExecutionResult:
        assert cell.cell_id == CellId("cell-1")
        assert cancellation.is_cancelled is False
        raise asyncio.CancelledError


def _event_kinds(path: Path) -> list[str]:
    return [
        json.loads(line)["kind"]
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def test_task_cancellation_terminalizes_durable_attempt_and_propagates(tmp_path: Path) -> None:
    cell = _cell()
    path = tmp_path / "events.jsonl"
    session = KernelExecutionSession(
        _request(cell),
        _TaskCancelledExecutor(),
        SessionPolicy(),
        JsonlExecutionEventSink(path),
        CancellationToken(),
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(session.run())

    assert _event_kinds(path) == [
        "session.started",
        "cell.started",
        "cell.cancelled",
        "session.cancelled",
    ]

    with pytest.raises(ValueError, match="session already started"):
        asyncio.run(session.run())
