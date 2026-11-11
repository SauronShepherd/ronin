"""Durable QueryFlux lifecycle invariants shared by HTTP and worker layers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

QueryFluxState = Literal["queued", "running", "cancelling", "succeeded", "failed", "cancelled"]
QueryFluxTerminalState = Literal["succeeded", "failed", "cancelled"]

_TRANSITIONS: dict[QueryFluxState, frozenset[QueryFluxState]] = {
    "queued": frozenset({"running", "cancelling", "failed", "cancelled"}),
    "running": frozenset({"cancelling", "succeeded", "failed", "cancelled"}),
    "cancelling": frozenset({"cancelled", "failed"}),
    "succeeded": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}


@dataclass(frozen=True, slots=True)
class QueryFluxExecution:
    """Identity and state needed to resume one scoped QueryFlux attempt."""

    workspace_id: str
    project_id: str
    run_id: str
    attempt_id: str
    state: QueryFluxState = "queued"
    cancel_requested: bool = False
    failure_code: str | None = None

    def request_cancel(self) -> QueryFluxExecution:
        """Record cancellation intent without mutating terminal executions."""

        if self.state in {"succeeded", "failed", "cancelled"}:
            return self
        if self.state == "cancelling":
            return replace(self, cancel_requested=True)
        return replace(self, state="cancelling", cancel_requested=True)

    def transition(
        self,
        state: QueryFluxState,
        *,
        failure_code: str | None = None,
    ) -> QueryFluxExecution:
        """Apply one lifecycle transition, rejecting illegal state changes."""

        if state == self.state:
            return replace(self, failure_code=failure_code or self.failure_code)
        if state == "succeeded" and self.cancel_requested:
            raise ValueError("a cancellation-requested QueryFlux execution cannot succeed")
        if state not in _TRANSITIONS[self.state]:
            raise ValueError(f"invalid QueryFlux transition: {self.state} -> {state}")
        if state == "failed" and not failure_code and not self.failure_code:
            raise ValueError("failed QueryFlux execution requires a failure_code")
        return replace(self, state=state, failure_code=failure_code or self.failure_code)

    @property
    def terminal(self) -> bool:
        return self.state in {"succeeded", "failed", "cancelled"}


__all__ = ("QueryFluxExecution", "QueryFluxState", "QueryFluxTerminalState")
