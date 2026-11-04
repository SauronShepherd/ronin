import pytest
from studio_ml.backends import BackendCapabilities, RemoteTrainingRequest
from studio_ml.remote import JsonRemoteBackend


def test_json_remote_backend_maps_provider_neutral_lifecycle() -> None:
    def transport(
        operation: str,
        payload: dict[str, object],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, object]:
        del timeout_seconds
        if operation == "predict":
            return {"predictions": [1, 2]}
        return {"run_id": payload.get("run_id", "r"), "status": "queued"}

    backend = JsonRemoteBackend(
        "remote.json", "JSON Remote", BackendCapabilities(("regression",), ("x",)), transport
    )
    request = RemoteTrainingRequest("dataset://x", "lab", 1, "x", idempotency_key="k")
    assert backend.submit(request).status == "queued"
    assert backend.predict("model", [{"x": 1}, {"x": 2}]) == [1, 2]


def test_remote_prediction_requires_exactly_one_result_per_input_row() -> None:
    def missing_prediction(
        _operation: str,
        _payload: dict[str, object],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, object]:
        del timeout_seconds
        return {"predictions": [1]}

    backend = JsonRemoteBackend(
        "remote.json",
        "JSON Remote",
        BackendCapabilities(("regression",), ("x",)),
        missing_prediction,
    )

    with pytest.raises(ValueError, match="prediction count must match"):
        backend.predict("model", [{"x": 1}, {"x": 2}])
