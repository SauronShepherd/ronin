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
