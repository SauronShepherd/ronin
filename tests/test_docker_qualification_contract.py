from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_local_docker_qualification_script_uses_immutable_image_and_real_suites() -> None:
    script = (ROOT / "tools" / "run_docker_qualification.ps1").read_text(encoding="utf-8")

    assert "docker build --file docker/Dockerfile" in script
    assert "docker image inspect $ImageTag --format '{{.Id}}'" in script
    assert "RONIN_DOCKER_QUALIFICATION_IMAGE" in script
    assert "tests/integration/test_worker_runtime_real.py" in script
    assert "tests/e2e/test_v01_journey.py" in script


def test_docker_image_normalizes_windows_line_endings_for_linux_entrypoint() -> None:
    dockerfile = (ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")

    assert "sed -i 's/\\r$//' /usr/local/bin/ronin-container-entrypoint" in dockerfile


def test_ci_docker_qualification_workflow_is_removed() -> None:
    assert not (ROOT / ".github" / "workflows" / "docker-qualification.yml").exists()


def test_dockerhub_publisher_restricts_mutable_aliases() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish-dockerhub.yml").read_text(
        encoding="utf-8"
    )

    assert "type: choice" in workflow
    assert "options:" in workflow
    assert "          - dev" in workflow
    assert "          - edge" in workflow
    assert 'case "$ALIAS" in' in workflow
    assert "dev|edge" in workflow
    assert "Refusing non-development Docker alias" in workflow
    assert "${{ inputs.alias }}" in workflow
