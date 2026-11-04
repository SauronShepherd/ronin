import json

import pytest
from studio_ml.backends import BackendCapabilities, RemoteTrainingRequest
from studio_ml.remote import (
    JsonRemoteBackend,
    RemoteExecutionController,
    urllib_json_transport,
)


def test_http_transport_rejects_unsafe_base_urls() -> None:
    with pytest.raises(ValueError, match="http or https"):
        urllib_json_transport("file:///tmp/provider")


def test_http_transport_caps_io_timeout_at_the_controller_deadline(monkeypatch) -> None:
    observed_timeouts: list[float] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit: int) -> bytes:
            return json.dumps({"run_id": "r", "status": "queued"}).encode()

    class Opener:
        def open(self, _request, *, timeout: float):
            observed_timeouts.append(timeout)
            return Response()

    monkeypatch.setattr("studio_ml.remote.build_opener", lambda _handler: Opener())
    transport = urllib_json_transport("https://ml.example.test", timeout_seconds=30)

    result = transport(
        "submit",
        {"request": {"timeout_seconds": 20}},
        timeout_seconds=4.25,
    )

    assert result == {"run_id": "r", "status": "queued"}
    assert observed_timeouts == [4.25]


def test_remote_controller_deadline_reaches_the_http_transport(monkeypatch) -> None:
    observed_timeouts: list[float] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit: int) -> bytes:
            return json.dumps({"run_id": "r", "status": "queued"}).encode()

    class Opener:
        def open(self, _request, *, timeout: float):
            observed_timeouts.append(timeout)
            return Response()

    monkeypatch.setattr("studio_ml.remote.build_opener", lambda _handler: Opener())
    transport = urllib_json_transport("https://ml.example.test", timeout_seconds=30)
    backend = JsonRemoteBackend(
        "remote.test",
        "Test provider",
        BackendCapabilities(("regression",), ("x",)),
        transport,
    )
    controller = RemoteExecutionController(backend, clock=lambda: 100.0)
    request = RemoteTrainingRequest(
        "dataset://x", "lab", 1, "x", timeout_seconds=9, idempotency_key="key"
    )

    assert controller.submit(request).status == "queued"
    assert observed_timeouts == [9.0]


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_http_transport_rejects_invalid_controller_deadlines(timeout: float) -> None:
    transport = urllib_json_transport("https://ml.example.test")
    with pytest.raises(ValueError, match="deadline timeout"):
        transport("submit", {"request": {"timeout_seconds": 10}}, timeout_seconds=timeout)
