from __future__ import annotations

import asyncio

from studio_runtime.plugin_worker import (
    WorkerContract,
    WorkerFailureKind,
    WorkerRequest,
    execute_worker,
)


def test_worker_returns_result_and_rejects_bounded_payload() -> None:
    async def run() -> None:
        request = WorkerRequest("example", "example.get.v1", {"value": 2}, "req-1")
        result = await execute_worker(request, lambda payload: payload["value"] * 2)
        assert result.payload == 4
        oversized = WorkerRequest("example", "example.get.v1", {"value": "x" * 100}, "req-2")
        rejected = await execute_worker(
            oversized, lambda payload: payload, contract=WorkerContract(max_payload_bytes=32)
        )
        assert rejected.failure is WorkerFailureKind.INVALID_PAYLOAD

    asyncio.run(run())


def test_worker_timeout_cancel_and_crash_are_stable() -> None:
    async def run() -> None:
        async def slow(_: object) -> object:
            await asyncio.sleep(0.05)
            return None

        request = WorkerRequest("example", "example.run.v1", {}, "req-3")
        timeout = await execute_worker(
            request, slow, contract=WorkerContract(timeout_seconds=0.001)
        )
        assert timeout.failure is WorkerFailureKind.TIMEOUT
        cancellation = asyncio.Event()
        cancellation.set()
        cancelled = await execute_worker(request, slow, cancellation=cancellation)
        assert cancelled.failure is WorkerFailureKind.CANCELLED
        crashed = await execute_worker(
            request, lambda _: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        assert crashed.failure is WorkerFailureKind.CRASH
        assert crashed.retryable is True

    asyncio.run(run())
