from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_duplicate_reservation_workflow_is_removed() -> None:
    assert not (ROOT / ".github" / "workflows" / "reserve-names.yml").exists()


def test_validation_workflows_are_removed_from_the_repository() -> None:
    workflows = ROOT / ".github" / "workflows"
    assert not tuple(workflows.glob("*.yml"))
    assert not tuple(workflows.glob("*.yaml"))
    for name in (
        "ci.yml",
        "docker-qualification.yml",
        "release-evidence.yml",
        "release-qualification.yml",
        "security.yml",
        "web-qualification.yml",
    ):
        assert not (workflows / name).exists()


def test_manual_release_runbook_replaces_automation() -> None:
    runbook = (ROOT / "docs" / "operations" / "MANUAL_RELEASE_AND_UPLOAD_RUNBOOK.md").read_text(
        encoding="utf-8"
    )
    assert "Ronin no utiliza GitHub Actions" in runbook
    assert "git push origin main" in runbook
