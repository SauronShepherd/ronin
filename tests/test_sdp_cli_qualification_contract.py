from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_sdp_cli_qualification.ps1"


def test_sdp_runner_uses_an_isolated_cli_data_root_and_fixture() -> None:
    script = RUNNER.read_text(encoding="utf-8")

    assert 'Join-Path $evidenceRoot "isolated-sdp-data"' in script
    assert '"SDPSTUDIO_DATA_ROOT"' in script
    assert "project create ronin-release-qualification --from-example retail-etl" in script
    assert "^[0-9A-Z]{26}$" in script


def test_sdp_runner_executes_the_exact_official_cli_integration_test() -> None:
    script = RUNNER.read_text(encoding="utf-8")

    assert "test_sdp_studio_real_cli_validation" in script
    assert "tests/e2e/test_data_engineering_external.py -k real_cli" in script
    assert '$skipped -ne 0' in script
    assert '$failed -ne 0' in script
    assert "$timingSummary.executed -ne 1" in script


def test_sdp_runner_keeps_separate_cli_streams_and_test_receipts() -> None:
    script = RUNNER.read_text(encoding="utf-8")

    assert '"project-create.stdout.txt"' in script
    assert '"project-create.stderr.txt"' in script
    assert '"sdp-junit.xml"' in script
    assert '"pytest-timings.json"' in script
    assert '"qualification.log"' in script
