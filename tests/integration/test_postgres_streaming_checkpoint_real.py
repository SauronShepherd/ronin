from __future__ import annotations

import os
from uuid import uuid4

import pytest
from studio_streaming import (
    PostgresStreamCheckpointStore,
    PostgresStreamTable,
    StreamBatch,
    StreamCheckpoint,
    StreamPosition,
    StreamRecord,
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
