from __future__ import annotations

import os
from uuid import uuid4

import pytest
from studio_streaming import PostgresStreamCheckpointStore, StreamCheckpoint, StreamPosition

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
