from pathlib import Path

import pytest

from studio_core import SourceRepository, safe_checkout_path


def test_source_repository_round_trip_payload_is_credential_free() -> None:
    source = SourceRepository("https://github.com/example/project.git", "a" * 40)
    assert source.to_payload() == {
        "uri": "https://github.com/example/project.git",
        "revision": "a" * 40,
    }


@pytest.mark.parametrize(
    "uri",
    [
        "https://user:password@example.test/repo.git",
        "https://example.test/repo.git?token=secret",
        "ftp://example.test/repo.git",
    ],
)
def test_source_repository_rejects_unsafe_locator(uri: str) -> None:
    with pytest.raises(ValueError, match="repository uri"):
        SourceRepository(uri, "main")


def test_source_repository_rejects_option_like_revision() -> None:
    with pytest.raises(ValueError, match="stable ref"):
        SourceRepository("file:///tmp/repo", "--upload-pack=evil")


def test_safe_checkout_path_rejects_escape_and_symlink(tmp_path: Path) -> None:
    root = tmp_path / "worktree"
    root.mkdir()
    assert safe_checkout_path(root, "src") == root / "src"
    with pytest.raises(ValueError, match="escapes"):
        safe_checkout_path(root, "../outside")
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "linked").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")
    with pytest.raises(ValueError, match="symlink"):
        safe_checkout_path(root, "linked")
