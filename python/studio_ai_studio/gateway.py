"""Buffered invocation gateway joining validation, routing and adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .contracts import Capability, PublicModelName
from .errors import CapabilityNotSupported, InvalidRequest
from .router import ModelRouter, RouteCandidate, RoutingStrategy


class Invoker(Protocol):
    def invoke(self, payload: Mapping[str, Any], model: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class Invocation:
    request_id: str
    model: PublicModelName
    operation: str
    payload: Mapping[str, Any]


class BufferedGateway:
    def __init__(self, router: ModelRouter, invokers: Mapping[str, Invoker]) -> None:
        self._router = router
        self._invokers = invokers

    def invoke(
        self,
        request: Invocation,
        candidates: Sequence[RouteCandidate],
        *,
        strategy: RoutingStrategy = RoutingStrategy.PRIORITY,
    ) -> Mapping[str, Any]:
        self._validate(request, candidates)
        decision = self._router.route(
            request.model, candidates, request_id=request.request_id, strategy=strategy
        )
        try:
            invoker = self._invokers.get(decision.endpoint_id.value)
            if invoker is None:
                raise InvalidRequest("selected endpoint has no configured adapter")
            response = invoker.invoke(request.payload, request.model.value)
            if not isinstance(response, Mapping):
                raise InvalidRequest("provider response must be a JSON object")
            return response
        finally:
            self._router.release(decision, request.request_id)

    @staticmethod
    def _validate(request: Invocation, candidates: Sequence[RouteCandidate]) -> None:
        required = {
            "chat": Capability.CHAT,
            "completion": Capability.COMPLETION,
            "embedding": Capability.EMBEDDING,
            "response": Capability.RESPONSE,
        }.get(request.operation)
        if required is None:
            raise InvalidRequest("unsupported operation")
        if not request.request_id or not request.model.value:
            raise InvalidRequest("request_id and model are required")
        if request.payload.get("model") != request.model.value:
            raise InvalidRequest("payload model does not match route model")
        matching = [item for item in candidates if item.snapshot.public_name == request.model]
        if not matching:
            raise InvalidRequest("model is not present in the catalog")
        if not any(required in item.snapshot.capabilities for item in matching):
            raise CapabilityNotSupported(required.value)
