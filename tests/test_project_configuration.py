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
    assert mutation["source_paths"] == ["src"]
    assert mutation["only_mutate"] == ["src/studio_core/*"]
    assert mutation["mutate_only_covered_lines"] is True
    data_files = config["tool"]["setuptools"]["data-files"]
    assert data_files["share/ronin/web"] == [
        "web/index.html",
        "web/routes.json",
        "web/README.md",
        "web/data-enginerring-studio.html",
        "web/data-enginerring-studio.css",
        "web/data-enginerring-studio.js",
        "web/throw-your-threads.html",
        "web/throw-your-threads.css",
        "web/throw-your-threads.js",
    ]
    assert data_files["share/ronin/web/assets"] == [
        "web/assets/ronin-logo-full.png",
        "web/assets/ronin-logo-mark.png",
        "web/assets/throw-your-threads/environment-atlas.webp",
        "web/assets/throw-your-threads/character-sheet.webp",
    ]
    assert set(data_files["share/ronin/web/js"]) == {
        f"web/js/{name}.js"
        for name in (
            "api",
            "a11y",
            "app",
            "alerts-studio",
            "cloud-studio",
            "catalog-studio",
            "command-palette",
            "connections-studio",
            "context-bar",
            "debugger-studio",
            "data-engineering-studio",
            "deployment-studio",
            "dom",
            "features",
            "environment-studio",
            "finops-studio",
            "graph-studio",
            "i18n",
            "quality-studio",
            "ingestion-studio",
            "notebook-studio",
            "scheduler-studio",
            "performance-studio",
            "project-journey",
            "studio-context",
            "semantic-studio",
            "streaming-studio",
            "synthetic-data-studio",
            "synthetic-journey",
            "tutorials",
            "ml-studio-journey",
            "ml-features-studio",
            "workspace-journey",
        )
    }
    assert data_files["share/ronin/web/styles"] == [
        "web/styles/base.css",
        "web/styles/components.css",
        "web/styles/layout.css",
        "web/styles/standalone-theme.css",
        "web/styles/tokens.css",
        "web/styles/tutorials.css",
    ]
    for skill in ("ronin-core", "ronin-data-engineering", "ronin-machine-learning"):
        prefix = f"share/ronin/agent-skills/{skill}"
        assert data_files[prefix] == [f"agent-skills/{skill}/SKILL.md"]
        assert data_files[f"{prefix}/agents"] == [f"agent-skills/{skill}/agents/openai.yaml"]
        assert len(data_files[f"{prefix}/references"]) == 1
        assert len(data_files[f"{prefix}/scripts"]) == 1

    compose = (root / "compose.yaml").read_text(encoding="utf-8")
    for variable in (
        "RONIN_ARTIFACT_BACKEND",
        "RONIN_S3_BUCKET",
        "RONIN_S3_PREFIX",
        "RONIN_S3_ENDPOINT_URL",
        "RONIN_S3_REGION",
    ):
        assert variable in compose
