from ronin_plugin_performance.service import analyze_http, analyze_performance


def test_service_returns_analysis_correlation_regression_and_practices():
    current = {
        "run_id": "new",
        "assets": [{"id": "a", "bytes": 1000, "file_count": 200}],
        "stages": [{"id": 1, "duration_ms": 120, "shuffle_write_bytes": 100}],
    }
    result = analyze_performance(
        {"run": current, "baseline": {"run_id": "old", "stages": [{"id": 1, "duration_ms": 100}]}}
    )
    assert result["schema"] == "ronin.performance-run/v1"
    assert result["correlation"]["schema"] == "ronin.performance-correlation/v1"
    assert result["regression"]["has_regressions"] is True
    assert {item["id"] for item in result["best_practices"]} >= {
        "partition-sizing",
        "file-compaction",
    }


def test_http_adapter_requires_object_body():
    result = analyze_http(body={"run_id": "http", "stages": []})
    assert result["run_id"] == "http"
