import pytest

from studio_streaming import StreamCheckpoint, StreamPosition, stream_health


def test_stream_health_reports_partition_lag():
    checkpoint = StreamCheckpoint((StreamPosition(0, 4), StreamPosition(1, 9)))
    health = stream_health("orders", checkpoint, latest_offsets={0: 5, 1: 9})
    assert health["lag"] == {"0": 1, "1": 0}
    assert health["total_lag"] == 1
    assert health["healthy"] is False


def test_stream_health_rejects_invalid_latest_offsets():
    checkpoint = StreamCheckpoint(())
    with pytest.raises(ValueError, match="latest offset"):
        stream_health("orders", checkpoint, latest_offsets={0: -2})


def test_stream_health_counts_unseen_partition_from_offset_minus_one():
    health = stream_health("orders", StreamCheckpoint(), latest_offsets={2: 3})
    assert health["lag"] == {"2": 4}
    assert health["total_lag"] == 4


def test_stream_health_serializes_partitions_in_deterministic_order() -> None:
    health = stream_health("orders", StreamCheckpoint(), latest_offsets={3: 0, 1: 2, 2: 1})
    assert tuple(health["lag"]) == ("1", "2", "3")
