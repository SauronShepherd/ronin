import pytest
from studio_ml.backends import (
    RemoteRetryPolicy,
    RemoteTrainingRequest,
    RemoteTrainingResult,
    RemoteTransientError,
)


def test_remote_training_contract_validates_limits_and_identity() -> None:
    request = RemoteTrainingRequest("dataset://x", "lab", 1, "spark.gbt", idempotency_key="k")
    assert request.timeout_seconds == 3600
    result = RemoteTrainingResult("run-1", "artifact://x", "sha256:abc", "queued")
    assert result.status == "queued"
    with pytest.raises(ValueError, match="idempotency"):
        RemoteTrainingRequest("dataset://x", "lab", 1, "spark.gbt")
    assert RemoteTransientError().retryable is True
    policy = RemoteRetryPolicy(max_attempts=4, initial_delay_seconds=2, max_delay_seconds=5)
    assert [policy.delay_for(attempt) for attempt in range(1, 5)] == [2, 4, 5, 5]
