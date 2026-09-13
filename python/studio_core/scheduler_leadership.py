"""Provider-neutral scheduler leadership lease contracts."""

from __future__ import annotations

from dataclasses import dataclass

from studio_orchestrator import Instant, LeaseToken


@dataclass(frozen=True, slots=True)
class SchedulerLeaderLease:
    """One deployment-local scheduler authority generation."""

    owner: str
    lease_token: LeaseToken
    generation: int
    acquired_at: Instant
    lease_expires_at: Instant

    def __post_init__(self) -> None:
        if not self.owner or self.owner != self.owner.strip():
            raise ValueError("scheduler leader owner must be non-empty and trimmed")
        if self.generation < 1:
            raise ValueError("scheduler leader generation must be positive")
        if self.lease_expires_at <= self.acquired_at:
            raise ValueError("scheduler leader lease must expire after acquisition")


__all__ = ("SchedulerLeaderLease",)
