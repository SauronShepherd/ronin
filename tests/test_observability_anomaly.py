import pytest
from studio_observability import detect_anomaly


def test_anomaly_hook_is_versioned_and_explainable():
    result = detect_anomaly("queue.lag", (1.0, 1.1, 0.9, 1.0), 10.0)
    assert result.anomalous is True
    assert result.schema == "ronin.observability.anomaly/v1"
    assert "median baseline" in result.reason
    assert result.to_payload()["anomalous"] is True


def test_anomaly_hook_rejects_unbounded_or_invalid_history():
    with pytest.raises(ValueError, match="history"):
        detect_anomaly("queue.lag", (), 1.0)
    with pytest.raises(ValueError, match="finite"):
        detect_anomaly("queue.lag", (1.0,), float("inf"))


def test_anomaly_extreme_finite_values_never_emit_non_finite_result():
    result = detect_anomaly("queue.lag", (1e308, 1e308), 0.0)
    assert result.baseline == 1e308
    assert all(
        value != float("inf") and value != float("-inf") and value == value
        for value in (result.baseline, result.deviation, result.threshold)
    )


def test_anomaly_rejects_boolean_threshold_and_values():
    with pytest.raises(ValueError, match="threshold"):
        detect_anomaly("queue.lag", (1.0,), 2.0, threshold=True)
    with pytest.raises(ValueError, match="finite"):
        detect_anomaly("queue.lag", (True,), 2.0)
