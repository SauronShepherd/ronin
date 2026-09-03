from dataclasses import FrozenInstanceError

import pytest
from studio_core import (
    CapabilityRequirement,
    ExecutionProfile,
    ProfileEvaluation,
    ResolvedRuntimeSnapshot,
    RuntimeCapability,
    RuntimeCatalog,
    RuntimeProfile,
    RuntimeProfileRef,
    RuntimeResolution,
    resolve_runtime,
    snapshot_runtime_resolution,
)
from studio_runners import (
    RuntimeDiscoveryIssue,
    RuntimeDiscoveryResult,
    discover_runtime_profiles,
)


def _profile(
    adapter_id: str,
    profile_id: str,
    *capabilities: RuntimeCapability,
    available: bool = True,
) -> RuntimeProfile:
    return RuntimeProfile(
        RuntimeProfileRef(adapter_id, profile_id),
        capabilities=capabilities,
        available=available,
    )


class _Adapter:
    def __init__(
        self,
        adapter_id: str,
        result: RuntimeDiscoveryResult | Exception,
        calls: list[str],
    ) -> None:
        self.adapter_id = adapter_id
        self._result = result
        self._calls = calls

    def discover(self) -> RuntimeDiscoveryResult:
        self._calls.append(self.adapter_id)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def test_discovery_evidence_validates_and_canonicalizes_adapter_output() -> None:
    for code, message, match in (
        ("", "safe", "issue code"),
        ("bad\ncode", "safe", "line breaks"),
        ("probe.failed", "", "issue message"),
        ("probe.failed", "bad\nmessage", "line breaks"),
    ):
        with pytest.raises(ValueError, match=match):
            RuntimeDiscoveryIssue(code, message)

    alpha = _profile("spark", "alpha")
    beta = _profile("spark", "beta")
    issue_a = RuntimeDiscoveryIssue("A", "first")
    issue_z = RuntimeDiscoveryIssue("Z", "last")
    result = RuntimeDiscoveryResult("spark", (beta, alpha), (issue_z, issue_a))
    assert result.profiles == (alpha, beta)
    assert result.issues == (issue_a, issue_z)

    with pytest.raises(ValueError, match="adapter id"):
        RuntimeDiscoveryResult(" ")
    with pytest.raises(ValueError, match="reporting adapter"):
        RuntimeDiscoveryResult("spark", (_profile("other", "default"),))
    with pytest.raises(ValueError, match="unique"):
        RuntimeDiscoveryResult("spark", (alpha, _profile("spark", "alpha")))


def test_discovery_is_stable_contains_provider_failures_and_builds_catalog() -> None:
    calls: list[str] = []
    local = _profile(
        "local",
        "default",
        RuntimeCapability("engine.spark"),
        RuntimeCapability("spark.version", "4.0"),
    )
    remote = _profile(
        "remote",
        "cluster",
        RuntimeCapability("engine.spark"),
        available=False,
    )
    report = discover_runtime_profiles(
        (
            _Adapter(
                "remote",
                RuntimeDiscoveryResult(
                    "remote",
                    (remote,),
                    (RuntimeDiscoveryIssue("runtime.unavailable", "remote is unavailable"),),
                ),
                calls,
            ),
            _Adapter("broken", RuntimeError("token=must-not-leak"), calls),
            _Adapter("local", RuntimeDiscoveryResult("local", (local,)), calls),
        )
    )

    assert calls == ["broken", "local", "remote"]
    assert report.catalog == RuntimeCatalog((local, remote))
    assert report.issues == (
        RuntimeDiscoveryIssue(
            "runtime.discovery_failed",
            "runtime discovery failed for adapter broken",
        ),
        RuntimeDiscoveryIssue("runtime.unavailable", "remote is unavailable"),
    )
    assert "token" not in " ".join(issue.message for issue in report.issues)


def test_discovery_rejects_invalid_duplicate_or_mismatched_adapter_identity() -> None:
    calls: list[str] = []
    with pytest.raises(ValueError, match="adapter id"):
        discover_runtime_profiles((_Adapter("\n", RuntimeDiscoveryResult("valid"), calls),))
    with pytest.raises(ValueError, match="unique"):
        discover_runtime_profiles(
            (
                _Adapter("same", RuntimeDiscoveryResult("same"), calls),
                _Adapter("same", RuntimeDiscoveryResult("same"), calls),
            )
        )
    assert calls == []

    mismatch = _Adapter("declared", RuntimeDiscoveryResult("reported"), calls)
    with pytest.raises(ValueError, match="does not match"):
        discover_runtime_profiles((mismatch,))


def test_resolved_runtime_snapshot_freezes_exact_selection_evidence() -> None:
    profile = _profile(
        "local",
        "default",
        RuntimeCapability("engine.spark"),
        RuntimeCapability("python.version", "3.12"),
    )
    intent = ExecutionProfile(
        runtime=profile.ref,
        requirements=(
            CapabilityRequirement("engine.spark"),
            CapabilityRequirement("python.version", ">=3.11", "preferred"),
        ),
    )
    resolution = resolve_runtime(intent, RuntimeCatalog((profile,)))
    snapshot = snapshot_runtime_resolution(intent, resolution)

    assert snapshot == ResolvedRuntimeSnapshot(
        requested_profile=profile.ref,
        resolved_profile=profile,
        resolution_policy="strict",
        exact_profile_selected=True,
        checks=resolution.evaluations[0].checks,
        preferred_matches=1,
    )
    assert snapshot is not None
    with pytest.raises(FrozenInstanceError):
        snapshot.preferred_matches = 0  # type: ignore[misc]


def test_resolved_runtime_snapshot_records_compatible_fallback_or_no_match() -> None:
    requested = _profile("remote", "requested", RuntimeCapability("spark.version", "3.5"))
    fallback = _profile("local", "fallback", RuntimeCapability("spark.version", "4.1"))
    intent = ExecutionProfile(
        runtime=requested.ref,
        requirements=(CapabilityRequirement("spark.version", ">=4"),),
        resolution="compatible",
    )
    resolution = resolve_runtime(intent, RuntimeCatalog((requested, fallback)))
    snapshot = snapshot_runtime_resolution(intent, resolution)
    assert snapshot is not None
    assert snapshot.requested_profile == requested.ref
    assert snapshot.resolved_profile == fallback
    assert snapshot.exact_profile_selected is False
    assert snapshot.resolution_policy == "compatible"

    no_match = resolve_runtime(
        ExecutionProfile(requirements=(CapabilityRequirement("gpu"),)),
        RuntimeCatalog((fallback,)),
    )
    assert snapshot_runtime_resolution(intent, no_match) is None


def test_snapshot_rejects_internally_inconsistent_resolution_evidence() -> None:
    profile = _profile("local", "default")
    other = _profile("local", "other")
    intent = ExecutionProfile(runtime=profile.ref)

    with pytest.raises(ValueError, match="no-match"):
        snapshot_runtime_resolution(
            intent,
            RuntimeResolution("no_match", profile, True, False, ()),
        )
    with pytest.raises(ValueError, match="requires a selected"):
        snapshot_runtime_resolution(
            intent,
            RuntimeResolution("selected", None, True, False, ()),
        )
    with pytest.raises(ValueError, match="resolution evidence"):
        snapshot_runtime_resolution(
            intent,
            RuntimeResolution("selected", profile, True, True, ()),
        )
    with pytest.raises(ValueError, match="must be compatible"):
        snapshot_runtime_resolution(
            intent,
            RuntimeResolution(
                "selected",
                profile,
                True,
                True,
                (ProfileEvaluation(profile, (), False, 0),),
            ),
        )
    with pytest.raises(ValueError, match="requested profile"):
        snapshot_runtime_resolution(
            intent,
            RuntimeResolution(
                "selected",
                other,
                True,
                True,
                (ProfileEvaluation(other, (), True, 0),),
            ),
        )
