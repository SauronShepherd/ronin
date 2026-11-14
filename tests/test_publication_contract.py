from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_docker_hub_publisher_defends_mutable_alias_allowlist_at_runtime() -> None:
    runbook = (ROOT / "docs" / "operations" / "MANUAL_RELEASE_AND_UPLOAD_RUNBOOK.md").read_text(
        encoding="utf-8"
    )
    assert "docker push" in runbook
    assert "Nunca usar alias mutables" in runbook
