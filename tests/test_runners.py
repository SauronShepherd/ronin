from __future__ import annotations

import asyncio
import sys

import pytest
from studio_kernel import CancellationToken
from studio_runners.container import AsyncioCommandRunner


def test_broken_stdin_reaps_process(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Stdin:
        def write(self, _data: bytes) -> None:
            return None

        async def drain(self) -> None:
            raise BrokenPipeError("child closed stdin")

        def close(self) -> None:
            return None

    class _Stdout:
        async def read(self, _limit: int) -> bytes:
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

    cleanup_args = ("docker", "rm", "-f", "ronin-test")
    with pytest.raises(BrokenPipeError, match="child closed stdin"):
        asyncio.run(
            AsyncioCommandRunner().run(
                ("docker", "run"),
                input_text="x" * 1024,
                cancellation=CancellationToken(),
                timeout_seconds=60.0,
                cancellation_args=cleanup_args,
            )
        )

    assert cleanup_calls == [cleanup_args]
    assert process.killed is True
    assert process.reaped is True


def test_truncation_keeps_prefix() -> None:
    outcome = asyncio.run(
        AsyncioCommandRunner(max_output_bytes=100).run(
            (sys.executable, "-c", "print('x' * 500, end='')"),
            input_text="",
            cancellation=CancellationToken(),
            timeout_seconds=2.0,
            cancellation_args=(sys.executable, "-c", "pass"),
        )
    )

    assert outcome.returncode == 0
    assert outcome.output.startswith("x" * 20)
    assert outcome.output.endswith("[OUTPUT TRUNCATED]")
    assert len(outcome.output) <= 100
