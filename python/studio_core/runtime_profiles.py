"""Deterministic, provider-neutral runtime profile advertisement and resolution."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from typing import Literal

from .projects import CapabilityRequirement, ExecutionProfile, RuntimeProfileRef

ResolutionStatus = Literal["selected", "no_match"]


def _require_text(value: str, field_name: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{field_name} must be non-empty and trimmed")
    if "\n" in value or "\r" in value:
        raise ValueError(f"{field_name} must not contain line breaks")


@dataclass(frozen=True, slots=True)
class RuntimeCapability:
    """One capability advertised by an execution adapter."""

    name: str
    value: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.name, "runtime capability name")
        if self.value is not None:
            _require_text(self.value, "runtime capability value")


@dataclass(frozen=True, slots=True)
class RuntimeProfile:
    """Pure snapshot of a concrete profile discovered by an adapter."""

    ref: RuntimeProfileRef
    capabilities: tuple[RuntimeCapability, ...] = ()
    available: bool = True

    def __post_init__(self) -> None:
        canonical = tuple(
            sorted(
                self.capabilities,
                key=lambda capability: (capability.name, capability.value or ""),
            )
        )
        names = [capability.name for capability in canonical]
        if len(names) != len(set(names)):
            raise ValueError("runtime capability names must be unique within a profile")
        object.__setattr__(self, "capabilities", canonical)

    def capability(self, name: str) -> RuntimeCapability | None:
        index = bisect_left(self.capabilities, name, key=lambda capability: capability.name)
        if index < len(self.capabilities) and self.capabilities[index].name == name:
            return self.capabilities[index]
        return None


@dataclass(frozen=True, slots=True)
class RuntimeCatalog:
    """Canonical set of adapter-advertised runtime profile snapshots."""

    profiles: tuple[RuntimeProfile, ...] = ()

    def __post_init__(self) -> None:
        canonical = tuple(
            sorted(
                self.profiles,
                key=lambda profile: (profile.ref.adapter_id, profile.ref.profile_id),
            )
        )
        refs = [profile.ref for profile in canonical]
        if len(refs) != len(set(refs)):
            raise ValueError("runtime profile references must be unique")
        object.__setattr__(self, "profiles", canonical)

    def get(self, ref: RuntimeProfileRef) -> RuntimeProfile | None:
        key = (ref.adapter_id, ref.profile_id)
        index = bisect_left(
            self.profiles,
            key,
            key=lambda profile: (profile.ref.adapter_id, profile.ref.profile_id),
        )
        if index < len(self.profiles) and self.profiles[index].ref == ref:
            return self.profiles[index]
        return None


@dataclass(frozen=True, slots=True)
class RequirementCheck:
    requirement: CapabilityRequirement
    advertised_value: str | None
    satisfied: bool
    reason: str


@dataclass(frozen=True, slots=True)
class ProfileEvaluation:
    profile: RuntimeProfile
    checks: tuple[RequirementCheck, ...]
    compatible: bool
    preferred_matches: int


@dataclass(frozen=True, slots=True)
class RuntimeResolution:
    status: ResolutionStatus
    selected: RuntimeProfile | None
    requested_profile_found: bool
    exact_profile_selected: bool
    evaluations: tuple[ProfileEvaluation, ...]


def resolve_runtime(intent: ExecutionProfile, catalog: RuntimeCatalog) -> RuntimeResolution:
    """Resolve execution intent without I/O, provider branches, or hidden fallback."""
    evaluations = tuple(_evaluate(profile, intent.requirements) for profile in catalog.profiles)
    requested = intent.runtime
    requested_profile = catalog.get(requested) if requested is not None else None
    requested_found = requested is None or requested_profile is not None

    if requested_profile is not None:
        exact = next(
            evaluation for evaluation in evaluations if evaluation.profile.ref == requested
        )
        if exact.compatible:
            return RuntimeResolution("selected", exact.profile, True, True, evaluations)
        if intent.resolution == "strict":
            return RuntimeResolution("no_match", None, True, False, evaluations)
    elif requested is not None and intent.resolution == "strict":
        return RuntimeResolution("no_match", None, False, False, evaluations)

    candidates = [evaluation for evaluation in evaluations if evaluation.compatible]
    if not candidates:
        return RuntimeResolution("no_match", None, requested_found, False, evaluations)
    selected = min(
        candidates,
        key=lambda evaluation: (
            -evaluation.preferred_matches,
            evaluation.profile.ref.adapter_id,
            evaluation.profile.ref.profile_id,
        ),
    )
    return RuntimeResolution("selected", selected.profile, requested_found, False, evaluations)


def _evaluate(
    profile: RuntimeProfile, requirements: tuple[CapabilityRequirement, ...]
) -> ProfileEvaluation:
    checks = tuple(
        _check(requirement, profile.capability(requirement.name)) for requirement in requirements
    )
    required_ok = all(check.satisfied for check in checks if check.requirement.level == "required")
    preferred_matches = sum(
        check.satisfied for check in checks if check.requirement.level == "preferred"
    )
    return ProfileEvaluation(
        profile=profile,
        checks=checks,
        compatible=profile.available and required_ok,
        preferred_matches=preferred_matches,
    )


def _check(
    requirement: CapabilityRequirement, capability: RuntimeCapability | None
) -> RequirementCheck:
    if capability is None:
        return RequirementCheck(requirement, None, False, "capability is not advertised")
    if requirement.constraint is None:
        return RequirementCheck(requirement, capability.value, True, "capability is advertised")
    if capability.value is None:
        return RequirementCheck(
            requirement,
            None,
            False,
            "constraint requires a capability value",
        )
    satisfied, reason = _matches_constraint(capability.value, requirement.constraint)
    return RequirementCheck(requirement, capability.value, satisfied, reason)


def _matches_constraint(value: str, constraint: str) -> tuple[bool, str]:
    terms = tuple(part.strip() for part in constraint.split(","))
    results = tuple(_matches_term(value, term) for term in terms)
    if any(result is None for result in results):
        return False, "ordered constraint requires numeric dotted advertised version"
    satisfied = all(result for result in results if result is not None)
    return satisfied, "constraint satisfied" if satisfied else "constraint not satisfied"


def _matches_term(value: str, term: str) -> bool | None:
    for operator in (">=", "<=", "==", "!=", ">", "<"):
        if term.startswith(operator):
            expected = term[len(operator) :].strip()
            if operator == "==":
                return value == expected
            if operator == "!=":
                return value != expected
            comparison = _compare_versions(value, expected)
            if comparison is None:
                return None
            if operator == ">=":
                return comparison >= 0
            if operator == "<=":
                return comparison <= 0
            if operator == ">":
                return comparison > 0
            return comparison < 0
    return value == term


def _compare_versions(left: str, right: str) -> int | None:
    left_parts = _numeric_version(left)
    right_parts = _numeric_version(right)
    if left_parts is None or right_parts is None:
        return None
    width = max(len(left_parts), len(right_parts))
    padded_left = left_parts + (0,) * (width - len(left_parts))
    padded_right = right_parts + (0,) * (width - len(right_parts))
    return (padded_left > padded_right) - (padded_left < padded_right)


def _numeric_version(value: str) -> tuple[int, ...] | None:
    parts = value.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)
