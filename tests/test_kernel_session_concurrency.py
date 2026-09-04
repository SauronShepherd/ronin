from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field

from studio_core import ResolvedRuntimeSnapshot, RuntimeProfile, RuntimeProfileRef
from studio_kernel import (
    CancellationSignal,
    CancellationToken,
    CellExecutionRequest,
    CellExecutionResult,
    ExecutionAttemptId,
    ExecutionEvent,
    ExecutionReproducibilitySnapshot,
    ExecutorIsolation,
    KernelDirective,
    KernelExecutionSession,
    NotebookExecutionRequest,
    RepositoryRevision,
    SessionPolicy,
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
    runtime = ResolvedRuntimeSnapshot(
        None,
        RuntimeProfile(RuntimeProfileRef("local", "python")),
        "compatible",
        False,
        (),
        0,
    )
    return NotebookExecutionRequest(
        NotebookDocument(Notebook(), ()),
        runtime,
        RepositoryRevision("a" * 40),
        ExecutionAttemptId("attempt-concurrent"),
        ExecutionReproducibilitySnapshot(),
        (cell,),
    )


@dataclass
class _Sink:
    events: list[ExecutionEvent] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def append(self, event: ExecutionEvent) -> None:
        with self.lock:
            self.events.append(event)


@dataclass
class _BlockingExecutor:
    entered: threading.Event
    release: threading.Event
    calls: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
    isolation: ExecutorIsolation = ExecutorIsolation("container", True, True, True)

    async def execute(
        self,
        cell: CellExecutionRequest,
        cancellation: CancellationSignal,
    ) -> CellExecutionResult:
        del cancellation
        with self.lock:
            self.calls += 1
        self.entered.set()
        await asyncio.to_thread(self.release.wait)
        return CellExecutionResult(cell.cell_id, "succeeded")


def test_session_start_is_atomic_across_concurrent_callers() -> None:
    entered = threading.Event()
    release = threading.Event()
    executor = _BlockingExecutor(entered, release)
    sink = _Sink()
    session = KernelExecutionSession(
        _request(),
        executor,
        SessionPolicy(),
        sink,
        CancellationToken(),
    )
    gate = threading.Barrier(3)
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()

    def caller() -> None:
        gate.wait()
        try:
            asyncio.run(session.run())
        except ValueError as exc:
            outcome = str(exc)
        else:
            outcome = "completed"
        with outcomes_lock:
            outcomes.append(outcome)

    first = threading.Thread(target=caller)
    second = threading.Thread(target=caller)
    first.start()
    second.start()
    gate.wait()
    assert entered.wait(timeout=2)
    release.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert sorted(outcomes) == ["completed", "session already started"]
    assert executor.calls == 1
    assert [event.kind for event in sink.events].count("session.started") == 1
    assert [event.event_id.sequence for event in sink.events] == [0, 1, 2]
