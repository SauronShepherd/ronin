from studio_migration import benchmark, decide_promotion, promotion_evidence


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
