from dataclasses import dataclass

from studio_ml.backends import (
    BackendCapabilities,
    RemoteTrainingRequest,
    RemoteTrainingResult,
    RemoteTransientError,
)
from studio_ml.remote import RemoteExecutionController


@dataclass
class FlakyBackend:
    attempts: int = 0
    backend_id: str = "flaky"
    display_name: str = "Flaky"
    capabilities: BackendCapabilities = BackendCapabilities(
        tasks=("regression",), algorithms=("x",)
    )

    def submit(self, _request: RemoteTrainingRequest) -> RemoteTrainingResult:
        self.attempts += 1
        if self.attempts < 2:
            raise RemoteTransientError("temporary")
        return RemoteTrainingResult("run", "artifact://run", "sha256:x", "queued")

    def poll(self, run_id: str) -> RemoteTrainingResult:
        return RemoteTrainingResult(run_id, "artifact://run", "sha256:x", "succeeded")

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
