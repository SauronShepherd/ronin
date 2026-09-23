"""Bounded capacity accounting and deterministic model routing."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock

from .contracts import EndpointConfig, EndpointId, ModelSnapshot, ObservedState, PublicModelName
from .errors import EndpointSaturated, ModelNotFound


class RoutingStrategy(StrEnum):
    PRIORITY = "priority"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    LEAST_IN_FLIGHT = "least_in_flight"


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    endpoint: EndpointConfig
    snapshot: ModelSnapshot
    state: ObservedState
    in_flight: int


@dataclass(frozen=True, slots=True)
class RouteDecision:
    endpoint_id: EndpointId
    public_model: PublicModelName
    strategy: RoutingStrategy
    attempt: int = 1


class CapacityLedger:
    """Thread-safe, bounded reservations; all releases are idempotent."""

    def __init__(self) -> None:
        self._counts: dict[EndpointId, int] = {}
        self._reservations: set[tuple[EndpointId, str]] = set()
        self._lock = Lock()

    def in_flight(self, endpoint_id: EndpointId) -> int:
        with self._lock:
            return self._counts.get(endpoint_id, 0)

    def reserve(self, endpoint: EndpointConfig, request_id: str) -> bool:
        key = (endpoint.id, request_id)
        with self._lock:
            if key in self._reservations:
                return True
            current = self._counts.get(endpoint.id, 0)
            if current >= endpoint.max_in_flight:
                return False
            self._reservations.add(key)
            self._counts[endpoint.id] = current + 1
            return True

    def release(self, endpoint_id: EndpointId, request_id: str) -> None:
        key = (endpoint_id, request_id)
        with self._lock:
            if key not in self._reservations:
                return
            self._reservations.remove(key)
            self._counts[endpoint_id] = max(0, self._counts.get(endpoint_id, 1) - 1)


class ModelRouter:
    def __init__(self, ledger: CapacityLedger | None = None) -> None:
        self.ledger = ledger or CapacityLedger()
        self._cursor: dict[PublicModelName, int] = {}

    def route(
        self,
        model: PublicModelName,
        candidates: Iterable[RouteCandidate],
        *,
        request_id: str,
        strategy: RoutingStrategy = RoutingStrategy.PRIORITY,
    ) -> RouteDecision:
        eligible = [
            candidate
            for candidate in candidates
            if candidate.snapshot.public_name == model
            and candidate.endpoint.desired_state.value == "enabled"
            and candidate.state in {ObservedState.READY, ObservedState.DEGRADED}
        ]
        if not eligible:
            raise ModelNotFound(model.value)
        if strategy is RoutingStrategy.PRIORITY:
            ordered = sorted(
                eligible, key=lambda item: (item.endpoint.priority, item.endpoint.id.value)
            )
        elif strategy is RoutingStrategy.LEAST_IN_FLIGHT:
            ordered = sorted(
                eligible,
                key=lambda item: (
                    self.ledger.in_flight(item.endpoint.id),
                    item.endpoint.priority,
                    item.endpoint.id.value,
                ),
            )
        else:
            ordered = sorted(eligible, key=lambda item: item.endpoint.id.value)
            index = self._cursor.get(model, 0) % len(ordered)
            self._cursor[model] = index + 1
            ordered = ordered[index:] + ordered[:index]
        for candidate in ordered:
            if self.ledger.reserve(candidate.endpoint, request_id):
                return RouteDecision(candidate.endpoint.id, model, strategy)
        raise EndpointSaturated(model.value)

    def release(self, decision: RouteDecision, request_id: str) -> None:
        self.ledger.release(decision.endpoint_id, request_id)
