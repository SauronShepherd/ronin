import json
from pathlib import Path

from tools.data_engineering_qualification import qualify


def test_configuration_schema_declares_external_runtime_settings() -> None:
    schema = json.loads(
        (Path(__file__).parents[1] / "python/studio_data_engineering/config.schema.json").read_text(
            encoding="utf-8"
        )
    )
    properties = schema["properties"]
    assert "spark_connect_endpoint" in properties
    assert "sdp_studio_command" in properties
    assert properties["external_provider_timeout_seconds"]["maximum"] == 3600


def test_qualification_probe_reports_external_environment_shape() -> None:
    result = qualify()
    assert set(result) == {
        "docker_cli",
        "spark_connect",
        "sdp_studio",
        "ready_for_external_e2e",
    }
    assert result["ready_for_external_e2e"] is False
