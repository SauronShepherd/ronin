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


def test_prerelease_promotes_the_qualified_digest_without_rebuilding() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish-prerelease.yml").read_text(
        encoding="utf-8"
    )
    assert (
        'docker buildx imagetools create --tag "$version_tag" "$IMAGE_NAME@$REGISTRY_DIGEST"'
        in workflow
    )
    assert (
        'docker buildx imagetools create --tag "$alpha_tag" "$IMAGE_NAME@$REGISTRY_DIGEST"'
        in workflow
    )
    assert (
        'docker buildx imagetools create --tag "$dev_tag" "$IMAGE_NAME@$REGISTRY_DIGEST"'
        in workflow
    )
    assert 'test "$version_digest" = "$REGISTRY_DIGEST"' in workflow
