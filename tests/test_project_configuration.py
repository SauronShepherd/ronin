from __future__ import annotations

import tomllib
from pathlib import Path


def test_project_configuration_preserves_validation_contract() -> None:
    root = Path(__file__).parents[1]
    with (root / "pyproject.toml").open("rb") as handle:
        config = tomllib.load(handle)

    project = config["project"]
    assert project["requires-python"] == ">=3.11"
    assert project["scripts"]["ronin"] == "studio_cli.entrypoint:main"
    assert "boto3>=1.35,<2" in project["optional-dependencies"]["data-plane"]

    packages = set(config["tool"]["mypy"]["packages"])
    assert {"studio_core", "studio_server", "studio_worker"} <= packages

    pytest = config["tool"]["pytest"]["ini_options"]
    assert pytest["testpaths"] == ["tests", "packages/pyronin/tests"]
    assert "e2e" in pytest["markers"][0]

    coverage = set(config["tool"]["coverage"]["run"]["source"])
    assert {"studio_core", "studio_server", "studio_worker", "pyronin"} <= coverage

    mutation = config["tool"]["mutmut"]
    assert mutation["source_paths"] == ["src/studio_core"]
    assert mutation["mutate_only_covered_lines"] is True
    assert config["tool"]["setuptools"]["data-files"]["share/ronin/web"] == [
        "web/index.html",
        "web/studio.css",
        "web/studio.js",
    ]

    compose = (root / "compose.yaml").read_text(encoding="utf-8")
    for variable in (
        "RONIN_ARTIFACT_BACKEND",
        "RONIN_S3_BUCKET",
        "RONIN_S3_PREFIX",
        "RONIN_S3_ENDPOINT_URL",
        "RONIN_S3_REGION",
    ):
        assert variable in compose
