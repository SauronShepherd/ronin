"""Immutable evidence for the runtime selected before an execution starts."""

from __future__ import annotations

from dataclasses import dataclass

from .projects import ExecutionProfile, ResolutionPolicy, RuntimeProfileRef
from .runtime_profiles import RequirementCheck, RuntimeProfile, RuntimeResolution


@dataclass(frozen=True, slots=True)
class ResolvedRuntimeSnapshot:
    """Provider-neutral record of the concrete runtime selected for one execution."""

    requested_profile: RuntimeProfileRef | None
    resolved_profile: RuntimeProfile
    resolution_policy: ResolutionPolicy
    exact_profile_selected: bool
    checks: tuple[RequirementCheck, ...]
    preferred_matches: int


def snapshot_runtime_resolution(
    intent: ExecutionProfile,
    resolution: RuntimeResolution,
) -> ResolvedRuntimeSnapshot | None:
    """Freeze a successful resolution without clocks, I/O, or provider metadata."""
    if resolution.status == "no_match":
        if resolution.selected is not None:
            raise ValueError("no-match runtime resolution must not contain a selected profile")
        return None
    if resolution.selected is None:
        raise ValueError("selected runtime resolution requires a selected profile")

    evaluation = next(
        (item for item in resolution.evaluations if item.profile.ref == resolution.selected.ref),
        None,
    )
    if evaluation is None:
        raise ValueError("selected runtime profile must have resolution evidence")
    if not evaluation.compatible:
        raise ValueError("selected runtime profile must be compatible")
    if resolution.exact_profile_selected and intent.runtime != resolution.selected.ref:
        raise ValueError("exact runtime selection must match the requested profile")

    return ResolvedRuntimeSnapshot(
        requested_profile=intent.runtime,
        resolved_profile=resolution.selected,
        resolution_policy=intent.resolution,
        exact_profile_selected=resolution.exact_profile_selected,
        checks=evaluation.checks,
        preferred_matches=evaluation.preferred_matches,
    )
