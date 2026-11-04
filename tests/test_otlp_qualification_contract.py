from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_otlp_qualification.ps1"


def test_otlp_runner_is_digest_pinned_and_loopback_only() -> None:
    script = RUNNER.read_text(encoding="utf-8")

    assert (
        "otel/opentelemetry-collector-contrib@sha256:"
        "45392d534c1edcc809c2d112394029246bc679d2ae5ea7081414a1fc74f2c621" in script
    )
    assert "^otel/opentelemetry-collector-contrib@sha256:[0-9a-f]{64}$" in script
    assert '--publish "127.0.0.1:${port}:4318"' in script
    assert "endpoint: 0.0.0.0:4318" in script


def test_otlp_runner_requires_the_real_telemetry_acceptance_test() -> None:
    script = RUNNER.read_text(encoding="utf-8")

    assert "test_real_otlp_collector_accepts_traces_metrics_and_logs" in script
    assert "$skipped -ne 0" in script
    assert "$failed -ne 0" in script
    assert "$missingTests.Count -gt 0" in script
    assert "$unexpectedTests.Count -gt 0" in script
    assert "$timingSummary.executed -ne $expectedTests.Count" in script


def test_otlp_runner_retains_timing_and_cleanup_evidence() -> None:
    script = RUNNER.read_text(encoding="utf-8")

    assert '"otlp-junit.xml"' in script
    assert '"pytest-timings.json"' in script
    assert '"collector-container.log"' in script
    assert "docker rm --force --volumes $containerName" in script
    assert '$cleanupStatus = "failed"' in script
    assert "service_startup = $startupSeconds" in script
    assert "pytest = $pytestSeconds" in script
    assert "cleanup = $cleanupSeconds" in script
