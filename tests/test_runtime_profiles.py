import pytest
from studio_core import (
    CapabilityRequirement,
    ExecutionProfile,
    RuntimeCapability,
    RuntimeCatalog,
    RuntimeProfile,
    RuntimeProfileRef,
    resolve_runtime,
)


def _profile(
    adapter: str,
    profile: str,
    *capabilities: RuntimeCapability,
    available: bool = True,
) -> RuntimeProfile:
    return RuntimeProfile(
        RuntimeProfileRef(adapter, profile),
        capabilities=capabilities,
        available=available,
    )


def test_runtime_capability_validates_and_profile_canonicalizes() -> None:
    with pytest.raises(ValueError, match="capability name"):
        RuntimeCapability("")
    with pytest.raises(ValueError, match="line breaks"):
        RuntimeCapability("bad\nname")
    with pytest.raises(ValueError, match="capability value"):
        RuntimeCapability("engine.spark", " ")
    with pytest.raises(ValueError, match="line breaks"):
        RuntimeCapability("engine.spark", "bad\nvalue")

    profile = _profile(
        "local",
        "default",
        RuntimeCapability("spark.version", "4.0"),
        RuntimeCapability("engine.spark"),
    )
    assert [capability.name for capability in profile.capabilities] == [
        "engine.spark",
        "spark.version",
    ]
    assert profile.capability("spark.version") == RuntimeCapability("spark.version", "4.0")
    assert profile.capability("missing") is None

    with pytest.raises(ValueError, match="unique"):
        _profile(
            "local",
            "duplicate",
            RuntimeCapability("spark.version", "4.0"),
            RuntimeCapability("spark.version", "3.5"),
        )


def test_runtime_catalog_is_canonical_and_rejects_duplicate_refs() -> None:
    alpha = _profile("adapter-a", "alpha")
    beta = _profile("adapter-b", "beta")
    catalog = RuntimeCatalog((beta, alpha))
    assert catalog.profiles == (alpha, beta)
    assert catalog.get(alpha.ref) == alpha
    assert catalog.get(RuntimeProfileRef("missing", "profile")) is None
    with pytest.raises(ValueError, match="unique"):
        RuntimeCatalog((alpha, _profile("adapter-a", "alpha")))


def test_strict_resolution_selects_exact_compatible_profile_with_evidence() -> None:
    requested = _profile(
        "spark-local",
        "default",
        RuntimeCapability("engine.spark"),
        RuntimeCapability("spark.version", "4.0.1"),
        RuntimeCapability("python.version", "3.12"),
    )
    intent = ExecutionProfile(
        runtime=requested.ref,
        requirements=(
            CapabilityRequirement("engine.spark"),
            CapabilityRequirement("spark.version", ">=4,<5"),
            CapabilityRequirement("python.version", ">=3.11", "preferred"),
        ),
    )
    resolution = resolve_runtime(intent, RuntimeCatalog((requested,)))
    assert resolution.status == "selected"
    assert resolution.selected == requested
    assert resolution.requested_profile_found is True
    assert resolution.exact_profile_selected is True
    evaluation = resolution.evaluations[0]
    assert evaluation.compatible is True
    assert evaluation.preferred_matches == 1
    assert [check.reason for check in evaluation.checks] == [
        "capability is advertised",
        "constraint satisfied",
        "constraint satisfied",
    ]


def test_strict_resolution_rejects_missing_or_incompatible_requested_profile() -> None:
    incompatible = _profile(
        "runtime",
        "old",
        RuntimeCapability("spark.version", "3.4"),
    )
    requirement = CapabilityRequirement("spark.version", ">=4")

    incompatible_result = resolve_runtime(
        ExecutionProfile(runtime=incompatible.ref, requirements=(requirement,)),
        RuntimeCatalog((incompatible,)),
    )
    assert incompatible_result.status == "no_match"
    assert incompatible_result.requested_profile_found is True
    assert incompatible_result.exact_profile_selected is False

    missing_result = resolve_runtime(
        ExecutionProfile(
            runtime=RuntimeProfileRef("runtime", "missing"),
            requirements=(requirement,),
        ),
        RuntimeCatalog((incompatible,)),
    )
    assert missing_result.status == "no_match"
    assert missing_result.requested_profile_found is False


def test_compatible_resolution_falls_back_without_relaxing_required_capabilities() -> None:
    requested = _profile(
        "runtime-z",
        "requested",
        RuntimeCapability("spark.version", "3.5"),
    )
    unavailable = _profile(
        "runtime-a",
        "unavailable",
        RuntimeCapability("spark.version", "4.0"),
        available=False,
    )
    fallback = _profile(
        "runtime-b",
        "fallback",
        RuntimeCapability("spark.version", "4.1"),
    )
    intent = ExecutionProfile(
        runtime=requested.ref,
        requirements=(CapabilityRequirement("spark.version", ">=4"),),
        resolution="compatible",
    )
    resolution = resolve_runtime(intent, RuntimeCatalog((requested, unavailable, fallback)))
    assert resolution.selected == fallback
    assert resolution.exact_profile_selected is False
    assert resolution.requested_profile_found is True

    missing_required = resolve_runtime(
        ExecutionProfile(
            runtime=requested.ref,
            requirements=(CapabilityRequirement("gpu"),),
            resolution="compatible",
        ),
        RuntimeCatalog((requested, unavailable, fallback)),
    )
    assert missing_required.status == "no_match"
    assert missing_required.selected is None


def test_compatible_resolution_can_fallback_when_requested_profile_is_missing() -> None:
    fallback = _profile("local", "default", RuntimeCapability("engine.spark"))
    resolution = resolve_runtime(
        ExecutionProfile(
            runtime=RuntimeProfileRef("remote", "missing"),
            requirements=(CapabilityRequirement("engine.spark"),),
            resolution="compatible",
        ),
        RuntimeCatalog((fallback,)),
    )
    assert resolution.selected == fallback
    assert resolution.requested_profile_found is False


def test_capability_only_resolution_ranks_preferred_matches_then_stable_ref() -> None:
    alpha = _profile(
        "adapter-a",
        "alpha",
        RuntimeCapability("engine.spark"),
        RuntimeCapability("gpu", "false"),
    )
    beta = _profile(
        "adapter-b",
        "beta",
        RuntimeCapability("engine.spark"),
        RuntimeCapability("gpu", "true"),
    )
    intent = ExecutionProfile(
        requirements=(
            CapabilityRequirement("engine.spark"),
            CapabilityRequirement("gpu", "true", "preferred"),
        ),
        resolution="compatible",
    )
    assert resolve_runtime(intent, RuntimeCatalog((alpha, beta))).selected == beta

    tie_intent = ExecutionProfile(
        requirements=(CapabilityRequirement("engine.spark"),),
        resolution="compatible",
    )
    tie = resolve_runtime(tie_intent, RuntimeCatalog((beta, alpha)))
    assert tie.selected == alpha
    assert tie.requested_profile_found is True
    assert tie.exact_profile_selected is False


def test_requirement_evidence_distinguishes_missing_value_and_failed_constraint() -> None:
    profile = _profile(
        "runtime",
        "minimal",
        RuntimeCapability("engine.spark"),
        RuntimeCapability("spark.version", "3.5"),
    )
    intent = ExecutionProfile(
        requirements=(
            CapabilityRequirement("engine.spark", "enabled", "preferred"),
            CapabilityRequirement("gpu", level="preferred"),
            CapabilityRequirement("spark.version", ">=4", "preferred"),
        ),
        resolution="compatible",
    )
    evaluation = resolve_runtime(intent, RuntimeCatalog((profile,))).evaluations[0]
    assert [check.advertised_value for check in evaluation.checks] == [None, None, "3.5"]
    assert [check.reason for check in evaluation.checks] == [
        "constraint requires a capability value",
        "capability is not advertised",
        "constraint not satisfied",
    ]
    assert evaluation.compatible is True
    assert evaluation.preferred_matches == 0


def test_constraint_grammar_supports_exact_inequality_and_numeric_ranges() -> None:
    profile = _profile(
        "runtime",
        "versions",
        RuntimeCapability("a", "4"),
        RuntimeCapability("b", "4"),
        RuntimeCapability("c", "4.0"),
        RuntimeCapability("d", "4.1"),
        RuntimeCapability("e", "3.9"),
        RuntimeCapability("f", "alpha"),
        RuntimeCapability("g", "alpha"),
    )
    intent = ExecutionProfile(
        requirements=(
            CapabilityRequirement("a", ">=4,<=4.0"),
            CapabilityRequirement("b", ">3.9,<4.1"),
            CapabilityRequirement("c", "==4.0"),
            CapabilityRequirement("d", "!=4.0"),
            CapabilityRequirement("e", "<4"),
            CapabilityRequirement("f", "alpha"),
            CapabilityRequirement("g", "!=beta"),
        )
    )
    result = resolve_runtime(intent, RuntimeCatalog((profile,)))
    assert result.status == "selected"
    assert all(check.satisfied for check in result.evaluations[0].checks)


def test_suffixed_versions_are_not_interpreted_by_core() -> None:
    for index, version in enumerate(
        (
            "14.3.x-scala2.12",
            "3.11.9rc1",
            "1.2.3-beta",
            "17-LTS",
            "3.5.0+build.1",
        )
    ):
        profile = _profile("runtime", f"version-{index}", RuntimeCapability("version", version))
        result = resolve_runtime(
            ExecutionProfile(requirements=(CapabilityRequirement("version", ">=1"),)),
            RuntimeCatalog((profile,)),
        )
        assert result.status == "no_match"
        check = result.evaluations[0].checks[0]
        assert check.satisfied is False
        assert check.reason == "ordered constraint requires numeric dotted advertised version"


def test_noncomparable_advertised_version_is_evidence_not_exception() -> None:
    profile = _profile("runtime", "named", RuntimeCapability("version", "latest"))
    result = resolve_runtime(
        ExecutionProfile(requirements=(CapabilityRequirement("version", ">=4"),)),
        RuntimeCatalog((profile,)),
    )
    assert result.status == "no_match"
    check = result.evaluations[0].checks[0]
    assert check.satisfied is False
    assert check.reason == "ordered constraint requires numeric dotted advertised version"
