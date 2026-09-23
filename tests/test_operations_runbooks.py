from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_upgrade_runbook_covers_forward_only_backup_and_rollback_boundary() -> None:
    text = (ROOT / "docs/operations/RONIN_UPGRADE_RUNBOOK.md").read_text(encoding="utf-8")
    for phrase in (
        "forward-only",
        "backup",
        "backup_deployment",
        "restore_deployment",
        "Rollback is limited",
        "migration",
    ):
        assert phrase in text


def test_failure_runbook_covers_required_operational_incidents() -> None:
    text = (ROOT / "docs/operations/RONIN_FAILURE_RUNBOOK.md").read_text(encoding="utf-8")
    for phrase in (
        "Stuck run",
        "Worker crash",
        "Database unavailable",
        "Artifact corruption",
        "Plugin degraded",
        "Provider degraded",
        "Scheduler split-brain risk",
        "Emergency disable",
    ):
        assert phrase in text
