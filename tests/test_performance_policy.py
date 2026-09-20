import pytest
from ronin_plugin_performance import PerformancePolicy, analyze_run


def test_policy_is_serializable_and_changes_findings():
    policy = PerformancePolicy(small_file_count=2, small_file_average_bytes=1000)
    result = analyze_run(
        {"run_id": "r", "assets": [{"id": "a", "bytes": 1500, "file_count": 2}]}, policy
    )
    assert result["policy"]["schema"] == "ronin.performance-policy/v1"
    assert "small-files" in {item["code"] for item in result["issues"]}


def test_policy_rejects_unknown_schema():
    with pytest.raises(ValueError, match="unsupported performance policy schema"):
        PerformancePolicy(schema="ronin.performance-policy/v9")
