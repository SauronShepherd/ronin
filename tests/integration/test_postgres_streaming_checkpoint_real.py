from __future__ import annotations

import os
from uuid import uuid4

import pytest
from studio_streaming import (
    MicroBatchProcessor,
    PostgresStreamCheckpointStore,
    PostgresStreamTable,
    StreamBatch,
    StreamCheckpoint,
    StreamPosition,
    StreamRecord,
    StreamSinkCommit,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("RONIN_POSTGRES_TEST_DSN"),
    reason="real PostgreSQL streaming checkpoint qualification requires RONIN_POSTGRES_TEST_DSN",
)


def test_postgres_stream_checkpoint_bundle_cas_and_reopen() -> None:
    store = PostgresStreamCheckpointStore(os.environ["RONIN_POSTGRES_TEST_DSN"])
    project_id = f"streaming-postgres-{uuid4().hex}"
    stream_id = f"events-{uuid4().hex}"
    runtime_id = store.runtime_stream_id(project_id, stream_id)
    assert store.get(runtime_id) == StreamCheckpoint()

    advanced = StreamCheckpoint((StreamPosition(0, 41), StreamPosition(1, 17)))
    assert store.compare_and_set(runtime_id, StreamCheckpoint(), advanced)
    assert not store.compare_and_set(runtime_id, StreamCheckpoint(), StreamCheckpoint())

    reopened = PostgresStreamCheckpointStore(os.environ["RONIN_POSTGRES_TEST_DSN"])
    assert reopened.get(runtime_id) == advanced
    assert not reopened.compare_and_set(
        runtime_id,
        StreamCheckpoint((StreamPosition(0, 40), StreamPosition(1, 17))),
        advanced,
    )


def test_postgres_stream_table_append_replay_and_conflict() -> None:
    table = PostgresStreamTable(os.environ["RONIN_POSTGRES_TEST_DSN"])
    stream_id = f"table-{uuid4().hex}"
    batch = StreamBatch(
        (StreamRecord(0, 7, 123, "key", {"event": "value"}),),
        StreamCheckpoint((StreamPosition(0, 7),)),
    )
    assert table.append(stream_id, batch) == 1
    assert table.append(stream_id, batch) == 0
    assert table.read(stream_id) == batch.records
    conflict = StreamBatch(
        (StreamRecord(0, 7, 123, "key", {"event": "different"}),),
        batch.checkpoint,
    )
    with pytest.raises(ValueError, match="replay conflicts"):
        table.append(stream_id, conflict)
    table.close()


def test_postgres_stream_table_reopen_replays_without_duplicate_rows() -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    stream_id = f"reopen-table-{uuid4().hex}"
    batch = StreamBatch(
        (StreamRecord(1, 13, 456, "reopen-key", {"event": "durable"}),),
        StreamCheckpoint((StreamPosition(1, 13),)),
    )
    first = PostgresStreamTable(dsn)
    try:
        assert first.append(stream_id, batch) == 1
    finally:
        first.close()

    reopened = PostgresStreamTable(dsn)
    try:
        assert reopened.append(stream_id, batch) == 0
        assert reopened.read(stream_id) == batch.records
    finally:
        reopened.close()


def test_postgres_stream_processor_reopens_with_durable_checkpoint() -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    stream_id = f"processor-reopen-{uuid4().hex}"
    batch = StreamBatch(
        (StreamRecord(0, 21, 789, "processor-key", {"event": "processed"}),),
        StreamCheckpoint((StreamPosition(0, 21),)),
    )

    class Source:
        def poll(self, checkpoint, *, limit, timeout_seconds):
            assert limit == 1
            assert timeout_seconds == 0.0
            return batch if not checkpoint.positions else StreamBatch((), checkpoint)

    class Sink:
        def __init__(self, table):
            self.table = table

        def write(self, current_stream_id, current_batch, rows):
            written = self.table.append(current_stream_id, current_batch)
            return StreamSinkCommit(
                f"postgres-batch:{current_batch.checkpoint.digest}",
                written,
                current_batch.checkpoint.digest,
            )

        def close(self):
            self.table.close()

    first_store = PostgresStreamCheckpointStore(dsn)
    first = MicroBatchProcessor(Source(), Sink(PostgresStreamTable(dsn)), first_store)
    try:
        result = first.run_once(stream_id, limit=1, timeout_seconds=0.0)
        assert result.records == 1
    finally:
        first.close()

    reopened_store = PostgresStreamCheckpointStore(dsn)
    reopened_table = PostgresStreamTable(dsn)
    second = MicroBatchProcessor(Source(), Sink(reopened_table), reopened_store)
    try:
        idle = second.run_once(stream_id, limit=1, timeout_seconds=0.0)
        assert idle.records == 0
        assert reopened_store.get(stream_id) == batch.checkpoint
        assert reopened_table.read(stream_id) == batch.records
    finally:
        second.close()
