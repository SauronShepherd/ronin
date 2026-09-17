from tools.performance_artifact import build_artifact


def test_performance_artifact_contains_diffable_latency_and_throughput() -> None:
    artifact = build_artifact(
        {"POST /v1/jobs": [0.001, 0.002, 0.004, 0.010]},
        sha="a" * 40,
        measured_at="2026-09-17T00:00:00+00:00",
    )

    metric = artifact["metrics"]["POST /v1/jobs"]
    assert metric["sample_count"] == 4
    assert metric["p50_ms"] == 2.0
    assert metric["p95_ms"] == 10.0
    assert metric["throughput_per_second"] == 235.294
    assert artifact["resources"] == {"cpu": None, "memory_bytes": None, "io_bytes": None}
