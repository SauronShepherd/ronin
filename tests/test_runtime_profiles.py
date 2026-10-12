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
    with pytest.raises(ValueError, match="line breaks"):
        RuntimeCapability("bad\rname")
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

    extension = RuntimeCapability("engine.spark", namespace="adapter.spark/v1")
    assert profile.capability("engine.spark") is not None
    assert profile.capability("engine.spark", "adapter.spark/v1") is None
    assert extension.namespace == "adapter.spark/v1"

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


def test_compatible_resolution_rejects_unknown_requested_profile() -> None:
    fallback = _profile("local", "default", RuntimeCapability("engine.spark"))
    resolution = resolve_runtime(
        ExecutionProfile(
            runtime=RuntimeProfileRef("remote", "missing"),
            requirements=(CapabilityRequirement("engine.spark"),),
            resolution="compatible",
        ),
        RuntimeCatalog((fallback,)),
    )
    assert resolution.status == "no_match"
    assert resolution.selected is None
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
    assert tie.selected is None
    assert tie.requested_profile_found is True
    assert tie.exact_profile_selected is False
    assert tie.status == "ambiguous"
    assert tie.selected is None


def test_capability_namespaces_prevent_cross_adapter_collisions() -> None:
    profile = _profile(
        "adapter",
        "default",
        RuntimeCapability("engine", "core", namespace="adapter.one/v1"),
        RuntimeCapability("engine", "core", namespace="adapter.two/v1"),
    )
    assert profile.capability("engine", "adapter.one/v1") == RuntimeCapability(
        "engine", "core", namespace="adapter.one/v1"
    )
    assert profile.capability("engine") is None


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


@pytest.mark.parametrize(
    ("advertised", "constraint", "satisfied"),
    [
        ("14.3.x-scala2.12", ">=14.3", True),
        ("14.3.x-scala2.12", ">=14.4", False),
        ("3.11.9rc1", ">=3.11", True),
        ("3.11.0rc1", ">=3.11.0", False),
        ("1.2.3-beta", ">=1.2", True),
        ("17-LTS", ">=17", True),
        ("3.5", ">=3.5.0", True),
    ],
)
def test_decorated_runtime_versions_resolve(
    advertised: str, constraint: str, satisfied: bool
) -> None:
    profile = _profile("runtime", "decorated", RuntimeCapability("version", advertised))
    result = resolve_runtime(
        ExecutionProfile(requirements=(CapabilityRequirement("version", constraint),)),
        RuntimeCatalog((profile,)),
    )
    check = result.evaluations[0].checks[0]
    assert check.satisfied is satisfied
    assert result.status == ("selected" if satisfied else "no_match")


def test_exact_equality_remains_exact_for_decorated_versions() -> None:
    profile = _profile("runtime", "decorated", RuntimeCapability("version", "14.3.x-scala2.12"))
    result = resolve_runtime(
        ExecutionProfile(requirements=(CapabilityRequirement("version", "==14.3"),)),
        RuntimeCatalog((profile,)),
    )
    assert result.status == "no_match"


def test_noncomparable_advertised_version_is_evidence_not_exception() -> None:
    profile = _profile("runtime", "named", RuntimeCapability("version", "latest"))
    result = resolve_runtime(
        ExecutionProfile(requirements=(CapabilityRequirement("version", ">=4"),)),
        RuntimeCatalog((profile,)),
    )
    assert result.status == "no_match"
    check = result.evaluations[0].checks[0]
    assert check.satisfied is False
    assert check.reason == "ordered constraint requires comparable advertised release"


def test_unavailable_requested_profile_is_not_selected() -> None:
    profile = _profile(
        "runtime",
        "offline",
        RuntimeCapability("engine.spark"),
        available=False,
    )
    result = resolve_runtime(
        ExecutionProfile(
            runtime=profile.ref,
            requirements=(CapabilityRequirement("engine.spark"),),
        ),
        RuntimeCatalog((profile,)),
    )
    assert result.status == "no_match"
    assert result.requested_profile_found is True
    assert result.exact_profile_selected is False


def test_resolution_evidence_is_preserved_for_no_match_and_ambiguity() -> None:
    profile = _profile("runtime", "offline", available=False)
    no_match = resolve_runtime(
        ExecutionProfile(requirements=(CapabilityRequirement("gpu"),)),
        RuntimeCatalog((profile,)),
    )
    assert no_match.status == "no_match"
    assert no_match.requested_profile_found is True
    assert no_match.exact_profile_selected is False
    assert len(no_match.evaluations) == 1
    assert no_match.evaluations[0].compatible is False

    alpha = _profile("a", "default", RuntimeCapability("engine"))
    beta = _profile("b", "default", RuntimeCapability("engine"))
    ambiguous = resolve_runtime(
        ExecutionProfile(requirements=(CapabilityRequirement("engine"),)),
        RuntimeCatalog((alpha, beta)),
    )
    assert ambiguous.status == "ambiguous"
    assert ambiguous.requested_profile_found is True
    assert len(ambiguous.evaluations) == 2


def test_unconstrained_capability_evidence_keeps_its_advertised_value() -> None:
    profile = _profile("runtime", "default", RuntimeCapability("engine", "spark"))
    result = resolve_runtime(
        ExecutionProfile(requirements=(CapabilityRequirement("engine"),)),
        RuntimeCatalog((profile,)),
    )

    assert result.evaluations[0].checks[0].advertised_value == "spark"
    assert result.evaluations[0].checks[0].reason == "capability is advertised"


@pytest.mark.parametrize(
    ("advertised", "constraint", "satisfied"),
    [
        ("4.1", "<=4.0", False),
        ("4.1", ">4.0", True),
        ("4.0", ">4.0", False),
        ("4.0", "<4.0", False),
        ("4.1", "!=4.0", True),
    ],
)
def test_runtime_constraint_boundaries_do_not_include_equal_or_greater_versions(
    advertised: str, constraint: str, satisfied: bool
) -> None:
    profile = _profile("runtime", "boundaries", RuntimeCapability("version", advertised))
    result = resolve_runtime(
        ExecutionProfile(requirements=(CapabilityRequirement("version", constraint),)),
        RuntimeCatalog((profile,)),
    )

    assert result.evaluations[0].checks[0].satisfied is satisfied


@pytest.mark.parametrize(
    ("value", "constraint", "satisfied"),
    [
        ("4.0", "<=4.0", True),
        ("4.0", "<4.0", False),
        ("4.0", ">4.0", False),
        ("4.0", "!=4.0", False),
        ("4.0", "!=3.0", True),
        ("4.0", "4.0", True),
        ("4.0", "4.1", False),
    ],
)
def test_runtime_constraint_operators_are_evaluated_independently(
    value: str, constraint: str, satisfied: bool
) -> None:
    profile = _profile("runtime", "constraints", RuntimeCapability("version", value))
    result = resolve_runtime(
        ExecutionProfile(requirements=(CapabilityRequirement("version", constraint),)),
        RuntimeCatalog((profile,)),
    )
    assert result.evaluations[0].checks[0].satisfied is satisfied


@pytest.mark.parametrize(
    "value",
    ["", " leading", "trailing ", "line\nfeed", "line\rfeed"],
)
def test_runtime_text_contract_rejects_unportable_values(value: str) -> None:
    with pytest.raises(ValueError, match="runtime capability"):
        RuntimeCapability(value)
    with pytest.raises(ValueError, match="runtime capability"):
        RuntimeCapability("engine", value)


def test_runtime_namespace_lookup_is_exact_and_capabilities_are_canonical() -> None:
    profile = _profile(
        "runtime",
        "namespaces",
        RuntimeCapability("engine", "spark", "adapter.one/v1"),
        RuntimeCapability("engine", "local", "adapter.two/v1"),
    )

    assert profile.capabilities[0].namespace == "adapter.one/v1"
    assert profile.capability("engine", "adapter.one/v1").value == "spark"
    assert profile.capability("engine", "adapter.two/v1").value == "local"
    assert profile.capability("engine") is None
