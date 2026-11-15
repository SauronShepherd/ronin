from pathlib import Path

import pytest
from studio_streaming import (
    SqliteStreamCheckpointStore,
    SqliteStreamTable,
    StreamBatch,
    StreamCheckpoint,
    StreamPosition,
    StreamRecord,
    window_records,
)


def test_window_records_rejects_missing_event_time_before_silent_drop() -> None:
    with pytest.raises(ValueError, match="explicit DLQ policy"):
        window_records(
            (StreamRecord(0, 1, None, None, {"value": 1}),),
            window_ms=1_000,
        )


def test_window_records_handles_large_late_batch_without_record_membership_scan() -> None:
    records = tuple(
        StreamRecord(0, offset, 1_000 + offset, None, {"value": offset}) for offset in range(2_000)
    )
    result = window_records(
        records,
        window_ms=1_000,
        previous_watermark_ms=2_000,
    )
    assert len(result.late_records) == 1_000
    assert sum(len(items) for _, items in result.windows) == 1_000


def test_stream_table_rejects_conflicting_replay(tmp_path: Path) -> None:
    table = SqliteStreamTable(tmp_path / "stream.sqlite")
    original = StreamRecord(0, 1, 1_000, "k", {"value": 1})
    batch = StreamBatch((original,), StreamCheckpoint((StreamPosition(0, 1),)))
    table.append("orders", batch)
    conflicting = StreamRecord(0, 1, 1_000, "k", {"value": 2})
    with pytest.raises(ValueError, match="replay conflicts"):
        table.append("orders", StreamBatch((conflicting,), batch.checkpoint))


def test_checkpoint_rejects_offset_regression_and_partition_removal(tmp_path: Path) -> None:
    store = SqliteStreamCheckpointStore(tmp_path / "checkpoint.sqlite")
    initial = StreamCheckpoint((StreamPosition(0, 10), StreamPosition(1, 20)))
    assert store.compare_and_set("orders", StreamCheckpoint(), initial)
    with pytest.raises(ValueError, match="move backwards"):
        store.compare_and_set(
            "orders",
            initial,
            StreamCheckpoint((StreamPosition(0, 9), StreamPosition(1, 20))),
        )
    with pytest.raises(ValueError, match="remove an existing partition"):
        store.compare_and_set("orders", initial, StreamCheckpoint((StreamPosition(0, 11),)))
    assert store.get("orders") == initial
    expanded = StreamCheckpoint(
        (StreamPosition(0, 11), StreamPosition(1, 20), StreamPosition(2, 0))
    )
    assert store.compare_and_set("orders", initial, expanded)
    assert store.get("orders") == expanded
