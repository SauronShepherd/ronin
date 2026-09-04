from __future__ import annotations

import asyncio
import sys

import pytest
from studio_kernel import CancellationToken
from studio_runners.container import AsyncioCommandRunner


def test_asyncio_task_cancellation_kills_and_reaps_child() -> None:
    async def scenario() -> None:
        runner = AsyncioCommandRunner(poll_seconds=0.005, cleanup_timeout_seconds=1.0)
        task = asyncio.create_task(
            runner.run(
                (sys.executable, "-c", "import time; time.sleep(30)"),
                input_text="",
                cancellation=CancellationToken(),
                timeout_seconds=60.0,
                cancellation_args=(sys.executable, "-c", "pass"),
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.done()

    asyncio.run(scenario())
