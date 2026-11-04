from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_spark_connect_qualification.ps1"


def test_spark_runner_uses_pinned_real_service_and_client_versions() -> None:
    script = RUNNER.read_text(encoding="utf-8")
    lock = (ROOT / "tools" / "spark-connect-client.lock").read_text(encoding="utf-8")

    assert "sha256:84a4eedb1abcf36a90808d5a1310e3e910b78c85d85aaa1599e31af5f862ed59" in script
    assert "ImageRef -notmatch '^sha256:[0-9a-f]{64}$'" in script
    assert "pyspark-client==4.2.0" in lock
    assert "pytz==2025.2" in lock
    assert "spark.connect.grpc.binding.port=15002" in script
    assert '--publish "127.0.0.1:${port}:15002"' in script


def test_spark_runner_executes_exact_live_test_and_rejects_skips() -> None:
    script = RUNNER.read_text(encoding="utf-8")

    assert "tests/e2e/test_data_engineering_external.py -k spark" in script
    assert "test_spark_connect_external_smoke" in script
    assert "$cases.Count -ne 1" in script
    assert "$skipped -ne 0" in script
    assert "$failed -ne 0" in script
    assert "$timingSummary.executed -ne 1" in script


def test_spark_runner_isolates_environment_and_retains_timed_evidence() -> None:
    script = RUNNER.read_text(encoding="utf-8")

    assert (
        'Join-Path $env:LOCALAPPDATA "Ronin\\qualification-cache\\spark-connect-client"' in script
    )
    assert '"spark-connect-client.lock"' in script
    assert "--require-hashes --no-deps" in script
    assert "Spark client dependency cache: hit" in script
    assert "--no-cache-dir" not in script
    assert '"SPARK_CONNECT_ENDPOINT", "PYTHONPATH"' in script
    assert '"pyspark-client-install.json"' in script
    assert '"spark-junit.xml"' in script
    assert '"pytest-timings.json"' in script
    assert '"spark-container.log"' in script
    assert "docker rm --force --volumes $containerName" in script
    assert '$cleanupStatus = "failed"' in script
