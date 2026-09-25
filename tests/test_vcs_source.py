from pathlib import Path

import pytest

from studio_vcs import SourcePolicyError, validate_repository_uri


@pytest.mark.parametrize("uri", ["https://example.test/repo.git", "ssh://git@example.test/repo"])
def test_validate_repository_uri_accepts_credential_free_git_uris(uri: str) -> None:
    assert validate_repository_uri(uri) == uri


@pytest.mark.parametrize(
    "uri",
    [
        "https://user:pass@example.test/repo",
        "ftp://example.test/repo",
        "https://example.test/repo?token=x",
    ],
)
def test_validate_repository_uri_rejects_credentials_unsupported_schemes_and_queries(
    uri: str,
) -> None:
    with pytest.raises(SourcePolicyError):
        validate_repository_uri(uri)


def test_source_policy_requires_a_local_path_to_be_a_git_repository(tmp_path: Path) -> None:
    from studio_vcs import capture_source_revision

    with pytest.raises(SourcePolicyError):
        capture_source_revision("file:///tmp/repo", tmp_path)


def test_validate_repository_uri_rejects_control_and_remote_file_forms() -> None:
    with pytest.raises(SourcePolicyError, match="control"):
        validate_repository_uri("https://example.test/repo\ngit.git")
    with pytest.raises(SourcePolicyError, match="remote host"):
        validate_repository_uri("file://server/share/repo.git")


def test_safe_checkout_path_rejects_escape_and_symlink_traversal(tmp_path: Path) -> None:
    from studio_core.source_control import safe_checkout_path

    (tmp_path / "src").mkdir()
    assert safe_checkout_path(tmp_path, "src") == (tmp_path / "src").resolve()
    with pytest.raises(ValueError, match="escapes"):
        safe_checkout_path(tmp_path, "../outside")

    outside = tmp_path.parent / f"ronin-source-outside-{tmp_path.name}"
    outside.mkdir()
    try:
        try:
            (tmp_path / "linked").symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            if getattr(exc, "winerror", None) == 1314:
                pytest.skip("symlink creation requires Windows developer privileges")
            raise
        with pytest.raises(ValueError, match="symlink"):
            safe_checkout_path(tmp_path, "linked")
    finally:
        outside.rmdir()
