from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_trino_qualification.ps1"


def test_trino_runner_uses_a_pinned_image_and_loopback_only() -> None:
    script = RUNNER.read_text(encoding="utf-8")

    assert (
        "trinodb/trino@sha256:2704eb53935af5e582d63d6033e9bf99d20c325e9b0e30b1016ef59a4773979f"
        in script
    )
    assert "^trinodb/trino@sha256:[0-9a-f]{64}$" in script
    assert '--publish "127.0.0.1:${port}:8080"' in script
    assert '$serverInfo.nodeVersion.version -eq "484"' in script
    assert "Add-Type -AssemblyName System.Net.Http" in script


def test_trino_runner_requires_exact_live_test_manifest_and_no_skips() -> None:
    script = RUNNER.read_text(encoding="utf-8")

    assert "test_trino_real_prepared_scalar_bindings" in script
    assert (
        "test_trino_real_result_byte_budget_accepts_exact_limit_and_rejects_one_byte_less" in script
    )
    assert "$skipped -ne 0" in script
    assert "$failed -ne 0" in script
    assert "$missingTests.Count -gt 0" in script
    assert "$unexpectedTests.Count -gt 0" in script
    assert "$timingSummary.executed -ne $expectedTests.Count" in script


def test_trino_runner_retains_evidence_and_checks_cleanup() -> None:
    script = RUNNER.read_text(encoding="utf-8")

    assert '"trino-junit.xml"' in script
    assert '"pytest-timings.json"' in script
    assert '"trino-container.log"' in script
    assert "docker rm --force --volumes $containerName" in script
    assert '$cleanupStatus = "failed"' in script
    assert "function Save-ContainerLogs" in script
    assert "Save-ContainerLogs -Name $containerName -Path $containerLogPath" in script
    assert "qualification_mode = $qualificationMode" in script
    assert "service_startup = $serviceStartupSeconds" in script
    assert "pytest = $pytestSeconds" in script
    assert "cleanup = $cleanupSeconds" in script
