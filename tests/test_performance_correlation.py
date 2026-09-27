from ronin_plugin_performance.correlation import compare_runs, correlate


def test_correlate_keeps_explicit_asset_and_runtime_lineage():
    result = correlate(
        {
            "run_id": "r",
            "assets": [{"id": "orders", "file_count": 2}],
            "runtimes": [{"id": "lava", "version": "0.1"}],
            "stages": [
                {"id": 1, "asset_ids": ["orders"], "runtime_id": "lava", "method_ids": ["a.b"]}
            ],
        }
    )
    assert result["rows"][0]["assets"][0]["id"] == "orders"
    assert result["rows"][0]["runtime"]["version"] == "0.1"


def test_compare_runs_detects_duration_and_shuffle_regression():
    baseline = {
        "run_id": "old",
        "stages": [{"id": 1, "duration_ms": 100, "shuffle_read_bytes": 100}],
    }
    current = {
        "run_id": "new",
        "stages": [{"id": 1, "duration_ms": 130, "shuffle_read_bytes": 140}],
    }
    result = compare_runs(current, baseline)
    assert result["has_regressions"] is True
    assert result["regressions"][0]["duration_delta"] == 0.3
