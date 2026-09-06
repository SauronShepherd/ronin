from __future__ import annotations

import asyncio
import time
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


@dataclass
class _SlowSyncSink:
    events: list[ExecutionEvent] = field(default_factory=list)

    def append(self, event: ExecutionEvent) -> None:
        time.sleep(0.05)
        self.events.append(event)


@dataclass
class _Executor:
    isolation: ExecutorIsolation = ExecutorIsolation(
        "container",
        True,
        True,
        True,
        "tested",
        "ronin/test-isolation",
        "1",
        "test-runtime",
        "test-evidence://isolation",
    )

    async def execute(
        self,
        cell: CellExecutionRequest,
        cancellation: CancellationSignal,
    ) -> CellExecutionResult:
        assert not cancellation.is_cancelled
        return CellExecutionResult(cell.cell_id, "succeeded")


def _request() -> NotebookExecutionRequest:
    cell = CellExecutionRequest(
        CellId("cell-1"),
        "print('ok')",
        "print('ok')",
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
        ExecutionAttemptId("attempt-async-sink"),
        ExecutionReproducibilitySnapshot(),
        (cell,),
    )


def test_sink_does_not_block_loop() -> None:
    sink = _SlowSyncSink()
    session = KernelExecutionSession(
        _request(), _Executor(), SessionPolicy(), sink, CancellationToken()
    )

    async def exercise() -> int:
        ticks = 0
        done = asyncio.Event()

        async def ticker() -> None:
            nonlocal ticks
            while not done.is_set():
                ticks += 1
                await asyncio.sleep(0.005)

        ticker_task = asyncio.create_task(ticker())
        await session.run()
        done.set()
        await ticker_task
        return ticks

    ticks = asyncio.run(exercise())
    assert ticks >= 5
    assert [event.kind for event in sink.events] == [
        "session.started",
        "cell.started",
        "cell.succeeded",
        "session.completed",
    ]
