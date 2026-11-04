from dataclasses import dataclass, field

import pytest
from studio_ml.backends import (
    BackendCapabilities,
    RemoteRetryPolicy,
    RemoteTrainingRequest,
    RemoteTrainingResult,
    RemoteTransientError,
)
from studio_ml.remote import RemoteExecutionController


@dataclass
class FlakyBackend:
    attempts: int = 0
    transient_failures: int = 1
    elapsed_per_call: float = 0.0
    clock_value: list[float] | None = None
    received_timeouts: list[float | None] = field(default_factory=list)
    backend_id: str = "flaky"
    display_name: str = "Flaky"
    capabilities: BackendCapabilities = BackendCapabilities(
        tasks=("regression",), algorithms=("x",)
    )

    def submit(
        self,
        _request: RemoteTrainingRequest,
        *,
        timeout_seconds: float | None = None,
    ) -> RemoteTrainingResult:
        self.attempts += 1
        self.received_timeouts.append(timeout_seconds)
        if self.clock_value is not None:
            self.clock_value[0] += self.elapsed_per_call
        if self.attempts <= self.transient_failures:
            raise RemoteTransientError("temporary")
        return RemoteTrainingResult("run", "artifact://run", "sha256:x", "queued")

    def poll(self, run_id: str) -> RemoteTrainingResult:
        return RemoteTrainingResult(run_id, "artifact://run", "sha256:" + "a" * 64, "succeeded")

    def cancel(self, run_id: str) -> RemoteTrainingResult:
        return RemoteTrainingResult(run_id, "artifact://run", "sha256:x", "cancelled")

    def predict(self, _model_ref: str, rows: list[dict[str, object]]) -> list[object]:
        return [0.0] * len(rows)


def test_remote_controller_retries_only_transient_submit_failures() -> None:
    backend = FlakyBackend()
    controller = RemoteExecutionController(backend)
    request = RemoteTrainingRequest("dataset://x", "lab", 1, "x", idempotency_key="key")
    assert controller.submit(request).status == "queued"
    assert backend.attempts == 2


def test_remote_controller_passes_the_remaining_deadline_to_each_attempt() -> None:
    clock_value = [10.0]
    backend = FlakyBackend(elapsed_per_call=2.25, clock_value=clock_value)
    controller = RemoteExecutionController(
        backend,
        RemoteRetryPolicy(max_attempts=2, initial_delay_seconds=0, max_delay_seconds=0),
        sleep=lambda _delay: None,
        clock=lambda: clock_value[0],
    )
    request = RemoteTrainingRequest(
        "dataset://x", "lab", 1, "x", timeout_seconds=5, idempotency_key="key"
    )

    assert controller.submit(request).status == "queued"
    assert backend.received_timeouts == [5.0, 2.75]


def test_remote_controller_rejects_a_result_returned_after_its_deadline() -> None:
    clock_value = [10.0]
    backend = FlakyBackend(transient_failures=0, elapsed_per_call=2.1, clock_value=clock_value)
    controller = RemoteExecutionController(backend, clock=lambda: clock_value[0])
    request = RemoteTrainingRequest(
        "dataset://x", "lab", 1, "x", timeout_seconds=2, idempotency_key="key"
    )

    with pytest.raises(RemoteTransientError, match="wall-clock budget expired"):
        controller.submit(request)
    assert backend.attempts == 1
    assert backend.received_timeouts == [2.0]
