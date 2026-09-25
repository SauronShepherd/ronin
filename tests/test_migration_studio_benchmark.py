import pytest

from studio_migration import (
    AnalyzerRegistry,
    AnalyzerSpec,
    RuntimeBuildFingerprint,
    benchmark,
    decide_promotion,
    promotion_evidence,
)


def test_analyzer_registry_is_deterministic_and_frozen() -> None:
    registry = AnalyzerRegistry()
    registry.add(AnalyzerSpec("pyspark.v1", "1.0", lambda _source: ()))
    assert [item.analyzer_id for item in registry.items] == ["pyspark.v1"]
    assert registry.analyze("pyspark.v1", "") == ()
    registry.freeze()
    with pytest.raises(ValueError, match="analyzer registry is frozen"):
        registry.add(AnalyzerSpec("other.v1", "1.0", lambda _source: ()))


def test_runtime_build_fingerprint_is_required_for_explicit_comparisons() -> None:
    runtime = RuntimeBuildFingerprint("spark", "3.5.1", "build-a", "sha256:image")
    baseline = benchmark(
        lambda: None, name="orders", measured_runs=1, runtime_build_fingerprint=runtime
    )
    candidate = benchmark(
        lambda: None,
        name="orders",
        measured_runs=1,
        runtime_build_fingerprint=RuntimeBuildFingerprint(
            "spark", "3.5.1", "build-b", "sha256:image"
        ),
    )

    decision = decide_promotion(
        "candidate",
        baseline=baseline,
        candidate=candidate,
        semantic_passed=True,
        quality_passed=True,
    )
    assert decision.reason == "runtime build fingerprints are incompatible"
    assert baseline.to_payload()["runtime_build_fingerprint"] == runtime.digest


def test_benchmark_records_median_and_environment_fingerprint() -> None:
    result = benchmark(
        lambda: sum(range(100)),
        name="orders",
        warmup_runs=1,
        measured_runs=3,
        fingerprint_inputs={"dataset": "fixture-v1"},
    )
    assert result.measured_runs == 3
    assert result.median_ms >= 0
    assert len(result.fingerprint) == 64


def test_optimizer_requires_semantics_quality_and_compatible_benchmark() -> None:
    baseline = benchmark(lambda: None, name="x", measured_runs=1, fingerprint_inputs={"v": 1})
    candidate = benchmark(lambda: None, name="x", measured_runs=1, fingerprint_inputs={"v": 1})
    decision = decide_promotion(
        "broadcast-1",
        baseline=baseline,
        candidate=candidate,
        semantic_passed=True,
        quality_passed=True,
    )
    assert decision.promoted is True
    rejected = decide_promotion(
        "bad", baseline=baseline, candidate=candidate, semantic_passed=False, quality_passed=True
    )
    assert rejected.promoted is False


def test_promotion_evidence_contains_both_runs_and_decision() -> None:
    baseline = benchmark(
        lambda: sum(range(10)), name="orders", measured_runs=1, fingerprint_inputs={"v": 1}
    )
    candidate = benchmark(
        lambda: sum(range(10)), name="orders", measured_runs=1, fingerprint_inputs={"v": 1}
    )
    decision = decide_promotion(
        "candidate-1",
        baseline=baseline,
        candidate=candidate,
        semantic_passed=True,
        quality_passed=True,
    )
    payload = promotion_evidence(
        decision,
        baseline=baseline,
        candidate=candidate,
        semantic_passed=True,
        quality_passed=True,
    )
    assert payload["schema"] == "ronin.migration.optimization-evidence/v1"
    assert payload["decision"]["candidate_id"] == "candidate-1"
    assert payload["baseline"]["fingerprint"] == payload["candidate"]["fingerprint"]
