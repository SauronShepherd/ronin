from ronin_plugin_performance.adapters import (
    normalize_madlava_snapshots,
    normalize_madmamba_records,
    normalize_spark_events,
)


def test_spark_adapter_preserves_stage_metrics():
    result = normalize_spark_events(
        [
            {
                "Event": "SparkListenerStageCompleted",
                "Stage Info": {
                    "Stage ID": 3,
                    "Accumulables": [
                        {"Name": "Shuffle Write Bytes", "Value": 42},
                        {"Name": "Disk Bytes Spilled", "Value": 7},
                    ],
                },
            }
        ]
    )
    assert result["schema"] == "ronin.performance-run/v1"
    assert result["stages"][0]["shuffle_write_bytes"] == 42
    assert result["stages"][0]["spill_disk_bytes"] == 7


def test_madmamba_and_madlava_adapters_are_bounded_and_normalized():
    mamba = normalize_madmamba_records(
        [{"recordType": "runtime.started", "payload": {"duration_ms": 12}}]
    )
    lava = normalize_madlava_snapshots(
        [
            {
                "snapshot": {"sequence": 1, "durationNanos": 2_000_000},
                "features": {"methodProfiling": {"a": {}}},
            }
        ]
    )
    assert mamba["stages"][0]["duration_ms"] == 12
    assert lava["stages"][0]["duration_ms"] == 2
    assert lava["stages"][0]["method_count"] == 1
