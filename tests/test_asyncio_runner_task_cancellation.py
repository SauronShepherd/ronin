from __future__ import annotations

import asyncio

import pytest
from studio_kernel import CancellationToken
from studio_runners.container import AsyncioCommandRunner


def test_asyncio_task_cancellation_kills_reaps_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Stdin:
        def write(self, _data: bytes) -> None:
            return None

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            return None

    class _Stdout:
        started: asyncio.Event

        def __init__(self) -> None:
            self.started = asyncio.Event()

        async def read(self, _limit: int) -> bytes:
            self.started.set()
            await asyncio.Event().wait()
            return b""

    class _Process:
        def __init__(self) -> None:
            self.stdin = _Stdin()
            self.stdout = _Stdout()
            self.returncode: int | None = None
            self.killed = False
            self.reaped = False
            self._done = asyncio.Event()

        async def wait(self) -> int:
            await self._done.wait()
            self.reaped = True
            return -9

        def kill(self) -> None:
            self.killed = True
            self.returncode = -9
            self._done.set()

    process = _Process()
    cleanup_calls: list[tuple[str, ...]] = []

    async def fake_create_subprocess_exec(*_args: str, **_kwargs: object) -> _Process:
        return process

    async def fake_cleanup(_self: AsyncioCommandRunner, args: tuple[str, ...]) -> None:
        cleanup_calls.append(args)

    monkeypatch.setattr(
        "studio_runners.container.asyncio.create_subprocess_exec", fake_create_subprocess_exec
    )
    monkeypatch.setattr(AsyncioCommandRunner, "_cleanup", fake_cleanup)

    async def scenario() -> None:
        runner = AsyncioCommandRunner(poll_seconds=0.005)
        cleanup_args = ("docker", "rm", "-f", "ronin-test")
        task = asyncio.create_task(
            runner.run(
                ("docker", "run"),
                input_text="",
                cancellation=CancellationToken(),
                timeout_seconds=60.0,
                cancellation_args=cleanup_args,
            )
        )
        await process.stdout.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cleanup_calls == [cleanup_args]
        assert process.killed is True
        assert process.reaped is True
        assert task.done()

    asyncio.run(scenario())


def test_task_cancellation_cleanup_is_idempotent_for_completed_process_and_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _CompletedProcess:
        returncode = 0
        killed = False

        def kill(self) -> None:
            self.killed = True

    cleanup_calls: list[tuple[str, ...]] = []

    async def fake_cleanup(_self: AsyncioCommandRunner, args: tuple[str, ...]) -> None:
        cleanup_calls.append(args)

    monkeypatch.setattr(AsyncioCommandRunner, "_cleanup", fake_cleanup)

    async def scenario() -> None:
        runner = AsyncioCommandRunner()
        process = _CompletedProcess()
        wait_task = asyncio.create_task(asyncio.sleep(0, result=0))
        output_task = asyncio.create_task(asyncio.sleep(0, result=(b"", False)))
        await asyncio.gather(wait_task, output_task)
        await runner._reap_after_task_cancellation(  # noqa: SLF001
            process,  # type: ignore[arg-type]
            wait_task,
            output_task,
            ("docker", "rm", "-f", "ronin-test"),
        )
        assert cleanup_calls == [("docker", "rm", "-f", "ronin-test")]
        assert process.killed is False
        assert wait_task.done()
        assert output_task.done()
        assert output_task.cancelled() is False

    asyncio.run(scenario())
