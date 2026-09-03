from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


@dataclass(frozen=True)
class _CrashingExecutor:
    isolation: ExecutorIsolation = ExecutorIsolation("container", True, True, True)

    def execute(
        self,
        cell: CellExecutionRequest,
        cancellation: CancellationSignal,
    ) -> CellExecutionResult:
        assert cell.cell_id == CellId("cell-1")
        assert cancellation.is_cancelled is False
        raise RuntimeError("raw-adapter-detail-must-not-reach-durable-evidence")


def test_executor_exception_is_normalized_without_persisting_raw_exception(tmp_path: Path) -> None:
    cell = CellExecutionRequest(
        CellId("cell-1"),
        "print('authored')",
        "print('executed')",
        "python",
        (),
        KernelDirective("test", "source.execute"),
    )
    request = NotebookExecutionRequest(
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
        ExecutionAttemptId("attempt-1"),
        ExecutionReproducibilitySnapshot(),
        (cell,),
    )
    event_path = tmp_path / "events.jsonl"

    results = KernelExecutionSession(
        request,
        _CrashingExecutor(),
        SessionPolicy(),
        JsonlExecutionEventSink(event_path),
        CancellationToken(),
    ).run()

    assert results == (CellExecutionResult(cell.cell_id, "failed", "kernel.executor.error"),)
    persisted = event_path.read_text(encoding="utf-8")
    assert "kernel.executor.error" in persisted
    assert "raw-adapter-detail-must-not-reach-durable-evidence" not in persisted
