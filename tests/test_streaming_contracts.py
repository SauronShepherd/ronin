from pathlib import Path

import pytest
from studio_streaming import (
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
