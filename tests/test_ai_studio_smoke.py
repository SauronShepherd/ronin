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


class SmokeInvoker:
    def invoke(self, _payload, model):
        return {"id": "smoke", "object": "chat.completion", "model": model, "choices": []}


def test_end_to_end_smoke_without_external_runtime():
    endpoint = EndpointConfig(
        EndpointId("fake"),
        AdapterKind.OPENAI_COMPATIBLE,
        "http://127.0.0.1:9000",
        (PublicModelName("smoke"),),
    )
    snapshot = ModelSnapshot(
        endpoint.id, "smoke", PublicModelName("smoke"), frozenset({Capability.CHAT})
    )
    candidate = RouteCandidate(endpoint, snapshot, ObservedState.READY, 0)
    api = AIStudioHTTPAPI(BufferedGateway(ModelRouter(), {"fake": SmokeInvoker()}), [candidate])
    response = api.dispatch("POST", "/v1/chat/completions", {"model": "smoke", "messages": []})
    assert response.status == 200
    assert response.body["object"] == "chat.completion"
