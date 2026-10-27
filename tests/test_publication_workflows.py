from pathlib import Path

ROOT = Path(__file__).parents[1]


def _workflow(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_dockerhub_publisher_only_accepts_explicit_mutable_aliases() -> None:
    workflow = _workflow("publish-dockerhub.yml")

    assert "type: choice" in workflow
    assert "options:\n          - dev\n          - edge" in workflow
    assert "inputs.tag" not in workflow
    assert "${{ inputs.alias }}" in workflow
    assert "environment: dockerhub-development" in workflow
    assert "@v" not in workflow


def test_duplicate_reservation_workflow_is_removed() -> None:
    assert not (ROOT / ".github" / "workflows" / "reserve-names.yml").exists()


def test_validation_workflows_are_removed_from_the_repository() -> None:
    workflows = ROOT / ".github" / "workflows"
    assert [path.name for path in workflows.glob("*.yml")] == ["publish-dockerhub.yml"]
    for name in (
        "ci.yml",
        "docker-qualification.yml",
        "release-evidence.yml",
        "release-qualification.yml",
        "security.yml",
        "web-qualification.yml",
    ):
        assert not (workflows / name).exists()
