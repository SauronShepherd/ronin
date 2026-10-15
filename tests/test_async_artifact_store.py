from __future__ import annotations

import asyncio
from threading import Event, get_ident
from typing import cast

import pytest
from studio_storage import (
    ArtifactRef,
    BoundedAsyncArtifactStore,
    LocalArtifactStore,
    StorageBackpressureError,
)

REF = ArtifactRef(
    role="cell-result",
    digest_algorithm="sha256",
    digest="a" * 64,
    media_type="application/json",
    size_bytes=2,
    storage_ref=f"artifact://sha256/{'a' * 64}",
)


class _BlockingArtifactStore:
    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()
        self.finished = Event()
        self.worker_thread_id: int | None = None

    def put_bytes(self, *, role: str, data: bytes, media_type: str | None = None) -> ArtifactRef:
        del role, data, media_type
        self.worker_thread_id = get_ident()
        self.started.set()
        try:
            if not self.release.wait(timeout=5):
                raise RuntimeError("test artifact store was not released")
        finally:
            self.finished.set()
        return REF

    def verify(self, ref: ArtifactRef) -> bool:
        return ref == REF


def _async_store(
    store: _BlockingArtifactStore,
    *,
    max_workers: int = 1,
    max_in_flight: int = 1,
) -> BoundedAsyncArtifactStore:
    return BoundedAsyncArtifactStore(
        cast(LocalArtifactStore, store),
        max_workers=max_workers,
        max_in_flight=max_in_flight,
    )


def test_artifact_io_is_off_loop_and_verification_round_trips() -> None:
    store = _BlockingArtifactStore()

    async def scenario() -> None:
        loop_thread_id = get_ident()
        async with _async_store(store) as artifacts:
            task = asyncio.create_task(
                artifacts.put_bytes(role="cell-result", data=b"{}", media_type="application/json")
            )
            await asyncio.to_thread(store.started.wait, 1)
            assert store.worker_thread_id is not None
            assert store.worker_thread_id != loop_thread_id
            store.release.set()
            assert await task == REF
            assert await artifacts.verify(REF)

    asyncio.run(scenario())


def test_artifact_capacity_exhaustion_fails_fast_and_cancel_keeps_slot_reserved() -> None:
    store = _BlockingArtifactStore()

    async def scenario() -> None:
        async with _async_store(store) as artifacts:
            task = asyncio.create_task(artifacts.put_bytes(role="cell-result", data=b"{}"))
            await asyncio.to_thread(store.started.wait, 1)

            with pytest.raises(StorageBackpressureError, match="capacity exhausted"):
                await artifacts.verify(REF)

            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            with pytest.raises(StorageBackpressureError, match="capacity exhausted"):
                await artifacts.verify(REF)

            store.release.set()
            assert await asyncio.to_thread(store.finished.wait, 1)
            await asyncio.sleep(0)
            assert await artifacts.verify(REF)

    asyncio.run(scenario())


def test_artifact_executor_bounds_and_closed_state_fail_closed() -> None:
    store = cast(LocalArtifactStore, _BlockingArtifactStore())
    with pytest.raises(ValueError, match="max_workers"):
        BoundedAsyncArtifactStore(store, max_workers=0)
    with pytest.raises(ValueError, match="max_in_flight"):
        BoundedAsyncArtifactStore(store, max_workers=2, max_in_flight=1)

    async def scenario() -> None:
        artifacts = BoundedAsyncArtifactStore(store, max_workers=1, max_in_flight=1)
        await artifacts.aclose()
        await artifacts.aclose()
        with pytest.raises(RuntimeError, match="closed"):
            await artifacts.verify(REF)

    asyncio.run(scenario())
