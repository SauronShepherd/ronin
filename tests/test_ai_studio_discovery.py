import sqlite3

from studio_ai_studio.contracts import (
    AdapterKind,
    EndpointConfig,
    EndpointId,
    ObservedState,
    PublicModelName,
)
from studio_ai_studio.discovery import DiscoveryWorker
from studio_ai_studio.storage import SQLiteAIStudioStore


class FakeTransport:
    def __init__(self, responses):
        self.responses = responses

    def get(self, url, *, timeout):  # noqa: ARG002
        return self.responses[url]


def endpoint(kind=AdapterKind.OPENAI_COMPATIBLE):
    return EndpointConfig(
        EndpointId("local"), kind, "http://127.0.0.1:8000", (PublicModelName("qwen"),)
    )


def test_probe_persists_models_and_ready_state():
    store = SQLiteAIStudioStore(sqlite3.connect(":memory:"))
    config = endpoint()
    store.put_endpoint(config)
    worker = DiscoveryWorker(
        store,
        FakeTransport({"http://127.0.0.1:8000/v1/models": (200, {"data": [{"id": "qwen"}]})}),
    )
    result = worker.probe(config)
    assert result.state is ObservedState.READY
    assert result.model_count == 1
    assert store.get_endpoint(config.id)[1] is ObservedState.READY


def test_failed_probe_is_reported_without_raising_to_scheduler():
    store = SQLiteAIStudioStore(sqlite3.connect(":memory:"))
    config = endpoint()
    store.put_endpoint(config)
    worker = DiscoveryWorker(
        store,
        FakeTransport({"http://127.0.0.1:8000/v1/models": (503, {})}),
    )
    result = worker.probe(config)
    assert result.state is ObservedState.FAILED
    assert "status 503" in result.detail
