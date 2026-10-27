from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_docker_hub_publisher_defends_mutable_alias_allowlist_at_runtime() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish-dockerhub.yml").read_text(
        encoding="utf-8"
    )
    assert 'case "$ALIAS"' in workflow
    assert "dev|edge" in workflow
    assert "Refusing non-development Docker alias" in workflow
    assert ":${{ inputs.alias }}" in workflow
