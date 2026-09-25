from dataclasses import dataclass

from studio_ml.backends import (
    BackendCapabilities,
    RemoteMLBackend,
    RemoteTrainingRequest,
    RemoteTrainingResult,
)


@dataclass
class FakeRemoteBackend:
    backend_id: str = "fake.remote"
    display_name: str = "Fake Remote"
    capabilities: BackendCapabilities = BackendCapabilities(
        tasks=("regression",), algorithms=("spark.gbt",), supports_artifacts=True
    )

    def submit(self, _request: RemoteTrainingRequest) -> RemoteTrainingResult:
        return RemoteTrainingResult("run-1", "artifact://run-1", "sha256:test", "queued")

    def poll(self, run_id: str) -> RemoteTrainingResult:
        return RemoteTrainingResult(run_id, "artifact://run-1", "sha256:test", "succeeded")

    def cancel(self, run_id: str) -> RemoteTrainingResult:
        return RemoteTrainingResult(run_id, "artifact://run-1", "sha256:test", "cancelled")

    def predict(self, _model_ref: str, rows: list[dict[str, object]]) -> list[object]:
        return [0.0 for _ in rows]


def test_remote_backend_protocol_is_runtime_checkable() -> None:
    backend = FakeRemoteBackend()
    assert isinstance(backend, RemoteMLBackend)
    request = RemoteTrainingRequest("dataset://x", "lab", 1, "spark.gbt", idempotency_key="k")
    assert backend.submit(request).status == "queued"
    assert backend.poll("run-1").status == "succeeded"
    assert backend.cancel("run-1").status == "cancelled"
