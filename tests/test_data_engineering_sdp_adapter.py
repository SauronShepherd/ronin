import json
import sys
from types import SimpleNamespace

from studio_data_engineering import SdpProjectSource, SdpStudioProvider


def test_sdp_project_import_is_lossless_and_content_addressed() -> None:
    source = SdpProjectSource(
        "retail",
        b"name: retail\n",
        ((".sdpstudio/pipelines/main.sdpstudio.yaml", b"nodes: []\n"),),
    )
    provider = SdpStudioProvider()
    report = provider.import_project(source)
    assert report.lossless is True
    assert report.source_digest == source.source_digest
    assert ".sdpstudio/project.yaml" in report.artifact_names
    assert provider.generated_artifact_names(source) == (
        "pipelines/main.sdpstudio.yaml",
        "ronin/sdp-source-digest.txt",
        "spark-pipeline.yaml",
        "transformations/generated.py",
    )


def test_sdp_validation_requires_explicit_compiler_provider() -> None:
    source = SdpProjectSource("retail", b"name: retail\n", ())
    result = SdpStudioProvider().validate(source)
    assert result["status"] == "provider_required"
    assert result["lossless"] is True


def test_sdp_provider_can_invoke_configured_cli(monkeypatch) -> None:
    calls = []

    def run(command, **kwargs):
        calls.append((command, json.loads(kwargs["input"])))
        return SimpleNamespace(returncode=0, stdout='{"valid":true}', stderr="")

    monkeypatch.setattr("studio_data_engineering.sdp_adapter.subprocess.run", run)
    source = SdpProjectSource("retail", b"name: retail\n", ())
    result = SdpStudioProvider(("sdp-studio", "compile")).compile(source)
    assert result == {"valid": True}
    assert calls[0][0] == ["sdp-studio", "compile"]
    assert calls[0][1]["action"] == "compile"


def test_sdp_provider_executes_real_json_subprocess() -> None:
    command = (
        sys.executable,
        "-c",
        "import json,sys; p=json.load(sys.stdin); "
        "print(json.dumps({'valid': p['action']=='validate'}))",
    )
    source = SdpProjectSource("retail", b"name: retail\n", ())
    result = SdpStudioProvider(command, timeout_seconds=5).validate(source)
    assert result["status"] == "valid"
    assert result["compiled"] == {"valid": True}
