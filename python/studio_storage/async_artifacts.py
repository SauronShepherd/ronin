"""Bounded non-blocking composition for the local artifact adapter."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import TypeVar

from studio_storage.artifacts import ArtifactRef, LocalArtifactStore
from studio_storage.async_store import StorageBackpressureError

_T = TypeVar("_T")


class BoundedAsyncArtifactStore:
    """Run synchronous artifact operations off-loop with bounded admission."""

    def __init__(
        self,
        store: LocalArtifactStore,
        *,
        max_workers: int = 2,
        max_in_flight: int = 4,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        if max_in_flight < max_workers:
            raise ValueError("max_in_flight must be greater than or equal to max_workers")
        self._store = store
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="ronin-artifact-store",
        )
        self._capacity_lock = asyncio.Lock()
        self._available_slots = max_in_flight
        self._closed = False

    async def __aenter__(self) -> BoundedAsyncArtifactStore:
        return self

    async def __aexit__(
        self,
        _exc_type: object,
        _exc: object,
        _traceback: object,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await asyncio.to_thread(self._executor.shutdown, wait=True, cancel_futures=False)

    async def put_bytes(
        self,
        *,
        role: str,
        data: bytes,
        media_type: str | None = None,
    ) -> ArtifactRef:
        return await self._call(
            partial(
                self._store.put_bytes,
                role=role,
                data=data,
                media_type=media_type,
            )
        )

    async def verify(self, ref: ArtifactRef) -> bool:
        return await self._call(partial(self._store.verify, ref))

    async def _reserve_slot(self) -> None:
        async with self._capacity_lock:
            if self._closed:
                raise RuntimeError("artifact-store executor is closed")
            if self._available_slots == 0:
                raise StorageBackpressureError("artifact-store execution capacity exhausted")
            self._available_slots -= 1

    def _release_slot(self, _future: object) -> None:
        self._available_slots += 1

    async def _call(self, operation: Callable[[], _T]) -> _T:
        await self._reserve_slot()
        loop = asyncio.get_running_loop()
        try:
            future = loop.run_in_executor(self._executor, operation)
        except BaseException:
            self._available_slots += 1
            raise
        future.add_done_callback(self._release_slot)
        return await asyncio.shield(future)


__all__ = ("BoundedAsyncArtifactStore",)
