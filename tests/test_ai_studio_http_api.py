from studio_ai_studio.contracts import (
    AdapterKind,
    Capability,
    EndpointConfig,
    EndpointId,
    ModelSnapshot,
    ObservedState,
    PublicModelName,
)
from studio_ai_studio.gateway import BufferedGateway
from studio_ai_studio.http_api import AIStudioHTTPAPI
from studio_ai_studio.router import ModelRouter, RouteCandidate


class Invoker:
    def invoke(self, _payload, model):  # noqa: ARG002
        return {"object": "chat.completion", "model": model}


def api():
    endpoint = EndpointConfig(
        EndpointId("local"), AdapterKind.OLLAMA, "http://127.0.0.1:8000", (PublicModelName("qwen"),)
    )
    snapshot = ModelSnapshot(
        endpoint.id, "qwen", PublicModelName("qwen"), frozenset({Capability.CHAT})
    )
    candidate = RouteCandidate(endpoint, snapshot, ObservedState.READY, 0)
    return AIStudioHTTPAPI(BufferedGateway(ModelRouter(), {"local": Invoker()}), [candidate])


def test_http_api_exposes_models_and_buffered_chat():
    service = api()
    assert service.dispatch("GET", "/v1/models").status == 200
    response = service.dispatch("POST", "/v1/chat/completions", {"model": "qwen"})
    assert response.status == 200
    assert response.body["model"] == "qwen"
