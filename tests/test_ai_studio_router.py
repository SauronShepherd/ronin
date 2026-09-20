import threading

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
from studio_ai_studio.errors import EndpointSaturated
from studio_ai_studio.router import CapacityLedger, ModelRouter, RouteCandidate


def candidate(name: str, priority: int, max_in_flight: int = 1) -> RouteCandidate:
    endpoint = EndpointConfig(
        EndpointId(name), AdapterKind.OLLAMA, f"http://127.0.0.1:{8000 + priority}",
        (PublicModelName("qwen"),), priority=priority, max_in_flight=max_in_flight,
    )
    snapshot = ModelSnapshot(
        endpoint.id, "qwen", PublicModelName("qwen"), frozenset({Capability.CHAT})
    )
    return RouteCandidate(endpoint, snapshot, ObservedState.READY, 0)


def test_priority_and_release_are_deterministic():
    router = ModelRouter()
    decision = router.route(
        PublicModelName("qwen"),
        [candidate("slow", 20), candidate("fast", 1)],
        request_id="r1",
    )
    assert decision.endpoint_id == EndpointId("fast")
    router.release(decision, "r1")
    assert router.ledger.in_flight(EndpointId("fast")) == 0


def test_capacity_falls_through_to_next_endpoint():
    router = ModelRouter()
    first = candidate("a", 1)
    second = candidate("b", 2)
    router.route(PublicModelName("qwen"), [first, second], request_id="r1")
    decision = router.route(PublicModelName("qwen"), [first, second], request_id="r2")
    assert decision.endpoint_id == EndpointId("b")


def test_concurrent_reservations_never_exceed_limit():
    ledger = CapacityLedger()
    endpoint = candidate("only", 1, 1).endpoint
    outcomes = []

    def reserve(index):
        outcomes.append(ledger.reserve(endpoint, f"r{index}"))

    threads = [threading.Thread(target=reserve, args=(index,)) for index in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(outcomes) == 1
    assert ledger.in_flight(endpoint.id) == 1


def test_saturated_model_is_retryable():
    router = ModelRouter()
    endpoint = candidate("only", 1)
    router.route(PublicModelName("qwen"), [endpoint], request_id="r1")
    with pytest.raises(EndpointSaturated):
        router.route(PublicModelName("qwen"), [endpoint], request_id="r2")
