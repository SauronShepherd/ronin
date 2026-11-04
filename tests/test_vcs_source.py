import shutil
import subprocess
from pathlib import Path

import pytest
from studio_vcs import SourcePolicyError, validate_repository_uri


def _git(path: Path, *args: str) -> str:
    completed = subprocess.run(  # noqa: S603
        (shutil.which("git") or "git", "-C", str(path), *args),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _repo_with_source(
    root: Path,
    *,
    origin: str,
    subdirectory: str = "",
) -> tuple[Path, str]:
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Ronin Test")
    _git(root, "config", "user.email", "ronin@example.invalid")
    source = root / subdirectory if subdirectory else root
    source.mkdir(parents=True, exist_ok=True)
    (source / "notebook.ronin.json").write_text("{}\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "initial")
    commit = _git(root, "rev-parse", "HEAD")
    _git(root, "remote", "add", "origin", origin)
    return source, commit


def test_capture_source_revision_matches_remote_identity_and_subdirectory(
    tmp_path: Path,
) -> None:
    from studio_vcs import capture_source_revision

    source, expected_commit = _repo_with_source(
        tmp_path / "checkout",
        origin="ssh://git@example.test/team/project.git",
        subdirectory="apps/demo",
    )
    evidence = capture_source_revision(
        "https://example.test/team/project",
        source,
        subdirectory="apps/demo",
    )

    assert evidence.uri == "https://example.test/team/project"
    assert evidence.revision.commit == expected_commit
    assert evidence.revision.dirty_patch_sha256 is None


def test_capture_source_revision_matches_local_file_remote_uri(tmp_path: Path) -> None:
    from studio_vcs import capture_source_revision

    remote = tmp_path / "upstream.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "-q")
    source, expected_commit = _repo_with_source(
        tmp_path / "checkout",
        origin=remote.as_uri(),
        subdirectory="src",
    )

    evidence = capture_source_revision(
        remote.as_uri(),
        source,
        subdirectory="src",
    )

    assert evidence.uri == remote.as_uri()
    assert evidence.revision.commit == expected_commit


def test_capture_source_revision_rejects_origin_mismatch(tmp_path: Path) -> None:
    from studio_vcs import capture_source_revision

    source, _ = _repo_with_source(
        tmp_path / "checkout",
        origin="https://other.example/team/project.git",
    )
    with pytest.raises(SourcePolicyError, match="does not match"):
        capture_source_revision("https://example.test/team/project.git", source)


def test_capture_source_revision_rejects_subdirectory_mismatch(tmp_path: Path) -> None:
    from studio_vcs import capture_source_revision

    source, _ = _repo_with_source(
        tmp_path / "checkout",
        origin="https://example.test/team/project.git",
        subdirectory="apps/actual",
    )
    with pytest.raises(SourcePolicyError, match="subdirectory"):
        capture_source_revision(
            "https://example.test/team/project",
            source,
            subdirectory="apps/declared",
        )


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
