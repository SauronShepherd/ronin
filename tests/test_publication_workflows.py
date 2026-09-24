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


def test_prerelease_publishing_actions_are_immutable() -> None:
    workflow = _workflow("publish-prerelease.yml")

    assert "actions/checkout@v" not in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" not in workflow
    assert "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33" in workflow
    assert "release-evidence" in workflow
    assert "vMAJOR.MINOR.PATCHaN" in workflow


def test_name_reservation_requires_explicit_non_release_confirmation() -> None:
    workflow = _workflow("publish-prerelease.yml")

    assert "reserve_confirmation:" in workflow
    assert "I_UNDERSTAND_RESERVED_ONLY" in workflow
    assert "inputs.reserve_confirmation == 'I_UNDERSTAND_RESERVED_ONLY'" in workflow


def test_tag_publication_requires_exact_aggregate_release_verdict() -> None:
    workflow = _workflow("publish-prerelease.yml")

    assert "authoritative-release-verdict:" in workflow
    assert "actions/workflows/release-evidence.yml/runs?head_sha=${GITHUB_SHA}" in workflow
    assert "name: exact-release-verdict" in workflow
    assert 'verdict.get("schema") != "ronin.release-verdict/v1"' in workflow
    assert 'verdict.get("commit") != os.environ["EXPECTED_COMMIT"]' in workflow
    assert 'verdict.get("status") != "passed"' in workflow
    for gate in (
        '"ci"',
        '"security"',
        '"status-consistency"',
        '"docker-qualification"',
        '"mutation"',
        '"browser"',
        '"a11y"',
        '"installed-artifact"',
        '"sbom-provenance"',
        '"license"',
        '"artifact-identity"',
    ):
        assert gate in workflow
    assert "- authoritative-release-verdict" in workflow
