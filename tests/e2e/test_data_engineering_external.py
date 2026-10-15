import os
import shutil
import subprocess

import pytest
from studio_data_engineering import (
    SdpProjectSource,
    SdpStudioProvider,
    SparkConnectProvider,
    execute_pipeline_job,
    persist_pipeline_evidence,
)
from studio_storage import LocalArtifactStore

_SPARK_ENDPOINT = os.environ.get("SPARK_CONNECT_ENDPOINT")
_SDP_COMMAND = os.environ.get("SDP_STUDIO_COMMAND")
_SDP_PROJECT_ID = os.environ.get("SDP_PROJECT_ID")

pytestmark = pytest.mark.e2e


@pytest.mark.skipif(not _SPARK_ENDPOINT, reason="SPARK_CONNECT_ENDPOINT is not configured")
def test_spark_connect_external_smoke(tmp_path) -> None:
    result = SparkConnectProvider(_SPARK_ENDPOINT).execute_sql("select 1", limit=1)
    assert result.row_count == 1
    worker = execute_pipeline_job(
        {
            "runtime": "spark-connect",
            "endpoint": _SPARK_ENDPOINT,
            "sql": "select 1 as value",
            "pipeline": {},
            "row_limit": 1,
        }
    )
    ref = persist_pipeline_evidence(
        LocalArtifactStore(tmp_path / "artifacts"),
        project_id="external-e2e",
        run_id="spark-connect-smoke",
        output=worker.output,
        evidence=worker.evidence,
    )
    assert ref.digest_algorithm == "sha256"
    assert ref.size_bytes > 0


@pytest.mark.skipif(not _SDP_COMMAND, reason="SDP_STUDIO_COMMAND is not configured")
def test_sdp_studio_external_smoke() -> None:
    source = SdpProjectSource("qualification", b"name: qualification\n", ())
    result = SdpStudioProvider(tuple(_SDP_COMMAND.split()), timeout_seconds=60).validate(source)
    assert result["status"] in {"valid", "invalid"}


@pytest.mark.skipif(
    not _SDP_PROJECT_ID,
    reason="SDP_PROJECT_ID is not configured for the real SDP Studio CLI",
)
def test_sdp_studio_real_cli_validation() -> None:
    completed = subprocess.run(  # noqa: S603 - explicit qualification CLI
        [shutil.which("sdpstudio") or "sdpstudio", "validate", _SDP_PROJECT_ID],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "Pipeline model is valid." in completed.stdout
