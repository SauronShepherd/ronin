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
