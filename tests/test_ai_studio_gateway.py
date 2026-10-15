import pytest
from studio_ai_studio.contracts import (
    AdapterKind,
    Capability,
    EndpointConfig,
    EndpointId,
    ModelSnapshot,
    ObservedState,
    PublicModelName,
)
from studio_ai_studio.errors import CapabilityNotSupported, InvalidRequest
from studio_ai_studio.gateway import BufferedGateway, Invocation
from studio_ai_studio.router import ModelRouter, RouteCandidate


class FakeInvoker:
    def __init__(self, response=None, error=None):
        self.response = response or {"object": "chat.completion"}
        self.error = error

    def invoke(self, _payload, _model):  # noqa: ARG002
        if self.error:
            raise self.error
        return self.response


def candidate(capabilities=frozenset({Capability.CHAT})):
    endpoint = EndpointConfig(
        EndpointId("local"), AdapterKind.OLLAMA, "http://127.0.0.1:8000", (PublicModelName("qwen"),)
    )
    model = ModelSnapshot(endpoint.id, "qwen", PublicModelName("qwen"), capabilities)
    return RouteCandidate(endpoint, model, ObservedState.READY, 0)


def request(operation="chat"):
    return Invocation("req-1", PublicModelName("qwen"), operation, {"model": "qwen"})


def test_gateway_invokes_and_always_releases_capacity():
    gateway = BufferedGateway(ModelRouter(), {"local": FakeInvoker({"ok": True})})
    assert gateway.invoke(request(), [candidate()]) == {"ok": True}
    assert gateway._router.ledger.in_flight(EndpointId("local")) == 0


def test_gateway_releases_capacity_when_upstream_fails():
    gateway = BufferedGateway(ModelRouter(), {"local": FakeInvoker(error=RuntimeError("upstream"))})
    with pytest.raises(RuntimeError, match="upstream"):
        gateway.invoke(request(), [candidate()])
    assert gateway._router.ledger.in_flight(EndpointId("local")) == 0


def test_gateway_rejects_missing_capability_before_reservation():
    gateway = BufferedGateway(ModelRouter(), {"local": FakeInvoker()})
    with pytest.raises(CapabilityNotSupported):
        gateway.invoke(request("embedding"), [candidate()])


def test_gateway_rejects_payload_model_mismatch():
    gateway = BufferedGateway(ModelRouter(), {"local": FakeInvoker()})
    invalid = Invocation("req-1", PublicModelName("qwen"), "chat", {"model": "other"})
    with pytest.raises(InvalidRequest, match="does not match"):
        gateway.invoke(invalid, [candidate()])
