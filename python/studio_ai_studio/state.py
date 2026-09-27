"""Endpoint readiness/capacity state transitions."""

from dataclasses import dataclass

from .contracts import ObservedState


@dataclass(frozen=True, slots=True)
class ProbeObservation:
    ready: bool
    has_capacity: bool | None = None
    hard_failure: bool = False


def transition(previous: ObservedState, observation: ProbeObservation) -> ObservedState:
    """Reduce an observation without conflating liveness and saturation."""
    if observation.hard_failure or not observation.ready:
        return ObservedState.FAILED
    if observation.has_capacity is False:
        return ObservedState.SATURATED
    if observation.has_capacity is None:
        return ObservedState.DEGRADED if previous is ObservedState.FAILED else ObservedState.READY
    return ObservedState.READY
