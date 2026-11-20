import pytest
from studio_streaming import (
    SqliteStreamTable,
    StreamBatch,
    StreamCheckpoint,
    StreamPosition,
    StreamRecord,
)


def test_stream_table_is_idempotent_and_bounded(tmp_path) -> None:
    record = StreamRecord(0, 1, 1000, "k", {"value": 1})
    batch = StreamBatch((record,), StreamCheckpoint((StreamPosition(0, 1),)))
    table = SqliteStreamTable(tmp_path / "stream.sqlite")
    assert table.append("events", batch) == 1
    assert table.append("events", batch) == 0
    assert table.read("events") == (record,)


def test_stream_table_batch_append_preserves_replay_conflict_detection(tmp_path) -> None:
    records = tuple(
        StreamRecord(0, offset, 1000 + offset, f"k-{offset}", {"value": offset})
        for offset in (1, 2, 3)
    )
    batch = StreamBatch(records, StreamCheckpoint((StreamPosition(0, 3),)))
    table = SqliteStreamTable(tmp_path / "stream.sqlite")
    assert table.append("events", batch) == 3
    assert table.append("events", batch) == 0

    conflicting = StreamBatch(
        (StreamRecord(0, 2, 1002, "k-2", {"value": "changed"}),),
        StreamCheckpoint((StreamPosition(0, 2),)),
    )
    with pytest.raises(ValueError, match="replay conflicts"):
        table.append("events", conflicting)
