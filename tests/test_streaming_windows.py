from studio_streaming import EventTimeWindow, StreamRecord, window_records


def test_event_time_windows_and_watermark_are_deterministic() -> None:
    records = tuple(StreamRecord(0, offset, timestamp, None, {"v": offset}) for offset, timestamp in ((0, 1_000), (1, 1_500), (2, 2_100)))
    result = window_records(records, window_ms=1_000, allowed_lateness_ms=100)
    assert result.watermark_ms == 2_000
    assert result.windows[0][0] == EventTimeWindow(1_000, 2_000)
    assert len(result.windows[0][1]) == 2


def test_late_records_are_classified_against_previous_watermark() -> None:
    record = StreamRecord(0, 0, 900, None, {})
    result = window_records((record,), window_ms=1_000, previous_watermark_ms=1_000)
    assert result.late_records == (record,)
    assert result.windows == ()
