import pytest
from studio_ai_studio.adapters import AdapterError, LlamaCppAdapter, OpenAICompatibleAdapter
from studio_ai_studio.contracts import AdapterKind, EndpointConfig, EndpointId, PublicModelName


class FakeTransport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, *, timeout):
        self.calls.append((url, timeout))
        return self.responses[url]


def config(adapter=AdapterKind.OPENAI_COMPATIBLE):
    return EndpointConfig(
        EndpointId("local"), adapter, "http://127.0.0.1:8000", (PublicModelName("qwen"),)
    )


def test_openai_probe_normalizes_models_and_is_bounded():
    transport = FakeTransport(
        {"http://127.0.0.1:8000/v1/models": (200, {"data": [{"id": "qwen"}]})}
    )
    result = OpenAICompatibleAdapter(transport, timeout=2).probe(config())
    assert result.ready is True
    assert result.models[0].public_name == PublicModelName("qwen")
    assert transport.calls == [("http://127.0.0.1:8000/v1/models", 2)]


def test_probe_rejects_malformed_provider_payload():
    transport = FakeTransport(
        {"http://127.0.0.1:8000/v1/models": (200, {"data": [{"name": "qwen"}]})}
    )
    with pytest.raises(AdapterError, match="id"):
        OpenAICompatibleAdapter(transport).probe(config())


def test_llama_readiness_is_separate_from_model_discovery():
    transport = FakeTransport(
        {
            "http://127.0.0.1:8000/v1/models": (200, {"data": [{"id": "qwen"}]}),
            "http://127.0.0.1:8000/health": (503, {}),
        }
    )
    result = LlamaCppAdapter(transport).probe(config(AdapterKind.LLAMA_CPP))
    assert result.ready is False
    assert result.models
