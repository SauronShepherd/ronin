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


def test_ci_docker_qualification_declares_postgres_and_real_worker_gate() -> None:
    workflow = (ROOT / ".github" / "workflows" / "docker-qualification.yml").read_text(
        encoding="utf-8"
    )

    assert "postgres:16" in workflow
    assert "RONIN_POSTGRES_TEST_DSN" in workflow
    assert "RONIN_TEST_POSTGRES_DSN" in workflow
    assert 'RONIN_REAL_DOCKER_QUALIFICATION: "1"' in workflow
    assert "tests/integration/test_worker_runtime_real.py" in workflow


def test_release_acceptance_runs_on_tag_commit_without_cross_workflow_artifact_assumptions() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish-prerelease.yml").read_text(
        encoding="utf-8"
    )
    assert "python -m pytest tests/e2e -m e2e -v --junitxml=acceptance-evidence/v01-acceptance.xml" in workflow
    assert "python -m tools.v01_acceptance_gate" in workflow
    assert "docker-qualification-${{ github.sha }}" not in workflow
    assert "v01-acceptance-provenance.json" not in workflow
