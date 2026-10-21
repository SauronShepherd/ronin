from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from studio_storage import PostgresArtifactReferenceBarrier

pytestmark = pytest.mark.skipif(
    not os.environ.get("RONIN_POSTGRES_TEST_DSN"),
    reason="real PostgreSQL retention barrier qualification requires RONIN_POSTGRES_TEST_DSN",
)


def test_collector_waits_for_writers_and_fences_new_writers() -> None:
    barrier = PostgresArtifactReferenceBarrier(
        os.environ["RONIN_POSTGRES_TEST_DSN"],
        application_name="ronin-retention-barrier-qualification",
    )
    writer_entered = Event()
    release_writer = Event()
    collector_entered = Event()
    writer_blocked_by_collector = Event()
    release_collector = Event()

    def write() -> None:
        with barrier.writer():
            writer_entered.set()
            assert release_writer.wait(timeout=10)

    def collect() -> None:
        with barrier.collector():
            collector_entered.set()
            assert release_collector.wait(timeout=10)

    def second_write() -> None:
        with barrier.writer():
            writer_blocked_by_collector.set()

    with ThreadPoolExecutor(max_workers=3) as executor:
        writer_future = executor.submit(write)
        assert writer_entered.wait(timeout=5)
        collector_future = executor.submit(collect)
        assert not collector_entered.wait(timeout=0.25)
        release_writer.set()
        writer_future.result(timeout=5)
        assert collector_entered.wait(timeout=5)

        second_writer_future = executor.submit(second_write)
        assert not writer_blocked_by_collector.wait(timeout=0.25)
        release_collector.set()
        collector_future.result(timeout=5)
        second_writer_future.result(timeout=5)
        assert writer_blocked_by_collector.is_set()


def test_async_worker_writer_blocks_collector_until_reference_commit() -> None:
    barrier = PostgresArtifactReferenceBarrier(
        os.environ["RONIN_POSTGRES_TEST_DSN"],
        application_name="ronin-async-worker-barrier-qualification",
    )
    collector_entered = Event()
    release_collector = Event()

    def collect() -> None:
        with barrier.collector():
            collector_entered.set()
            assert release_collector.wait(timeout=10)

    async def exercise() -> None:
        with ThreadPoolExecutor(max_workers=1) as executor:
            async with barrier.awriter():
                collector_future = executor.submit(collect)
                assert not await asyncio.to_thread(collector_entered.wait, 0.25)
            assert await asyncio.to_thread(collector_entered.wait, 5)
            release_collector.set()
            await asyncio.to_thread(collector_future.result, 5)

    asyncio.run(exercise())
