from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tools.ronin_candidate_boundary import (
    CandidateBoundaryError,
    cleanup_candidate,
    generate_candidate,
    verify_candidate,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(  # noqa: S603, S607 - tests invoke fixed Git commands
        ["git", "-C", str(repo), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _source_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "source"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.email", "ronin-tests@example.invalid")
    _git(repo, "config", "user.name", "Ronin tests")
    (repo / "tracked.txt").write_bytes(b"tracked content\n")
    (repo / "nested").mkdir()
    (repo / "nested" / "executable.sh").write_bytes(b"#!/bin/sh\necho ok\n")
    _git(repo, "add", "tracked.txt", "nested/executable.sh")
    _git(repo, "update-index", "--chmod=+x", "nested/executable.sh")
    _git(repo, "commit", "-m", "candidate source")
    source_sha = _git(repo, "rev-parse", "HEAD")
    return repo, source_sha


def test_generation_binds_exact_commit_excludes_untracked_and_has_no_git_metadata(
    tmp_path: Path,
) -> None:
    repo, source_sha = _source_repo(tmp_path)
    (repo / "UNTRACKED-SENTINEL.txt").write_text("must not ship", encoding="utf-8")
    output = tmp_path / "candidate-one"

    artifacts = generate_candidate(source_sha, output, repo=repo)
    verification = verify_candidate(output, repo=repo)
    manifest = json.loads(artifacts.manifest.read_text(encoding="utf-8"))

    assert verification.source_sha == source_sha
    assert manifest["source_sha"] == source_sha
    assert manifest["file_count"] == 2
    assert [entry["path"] for entry in manifest["files"]] == [
        "nested/executable.sh",
        "tracked.txt",
    ]
    assert not (artifacts.sandbox / "UNTRACKED-SENTINEL.txt").exists()
    assert not (artifacts.sandbox / ".git").exists()
    assert not any(path.name == ".git" for path in artifacts.sandbox.rglob("*"))
    assert artifacts.archive.parent != repo
    assert artifacts.archive.parent not in repo.parents


def test_archive_manifest_listing_and_digest_are_reproducible(tmp_path: Path) -> None:
    repo, source_sha = _source_repo(tmp_path)

    first = generate_candidate(source_sha, tmp_path / "candidate-first", repo=repo)
    second = generate_candidate(source_sha, tmp_path / "candidate-second", repo=repo)

    assert first.archive.read_bytes() == second.archive.read_bytes()
    assert first.manifest.read_bytes() == second.manifest.read_bytes()
    assert first.digest_file.read_bytes() == second.digest_file.read_bytes()
    assert (
        hashlib.sha256(first.archive.read_bytes()).hexdigest()
        == json.loads(first.manifest.read_text(encoding="utf-8"))["archive"]["sha256"]
    )
    assert verify_candidate(first.output_dir, repo=repo).file_count == 2
    assert verify_candidate(second.output_dir, repo=repo).file_count == 2


def test_verification_works_without_git_metadata_or_repository(tmp_path: Path) -> None:
    repo, source_sha = _source_repo(tmp_path)
    artifacts = generate_candidate(source_sha, tmp_path / "candidate", repo=repo)

    verification = verify_candidate(artifacts.output_dir)

    assert verification.source_sha == source_sha
    assert verification.file_count == 2


def test_verify_rejects_archive_tampering(tmp_path: Path) -> None:
    repo, source_sha = _source_repo(tmp_path)
    artifacts = generate_candidate(source_sha, tmp_path / "candidate", repo=repo)
    with artifacts.archive.open("ab") as stream:
        stream.write(b"tampered")

    with pytest.raises(CandidateBoundaryError, match="archive digest|archive does not match"):
        verify_candidate(artifacts.output_dir, repo=repo)


def test_verify_rejects_manifest_tampering(tmp_path: Path) -> None:
    repo, source_sha = _source_repo(tmp_path)
    artifacts = generate_candidate(source_sha, tmp_path / "candidate", repo=repo)
    payload = json.loads(artifacts.manifest.read_text(encoding="utf-8"))
    payload["total_bytes"] += 1
    artifacts.manifest.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(CandidateBoundaryError, match="canonical|manifest digest|total_bytes"):
        verify_candidate(artifacts.output_dir, repo=repo)


def test_verify_rejects_untracked_sandbox_file_and_git_metadata(tmp_path: Path) -> None:
    repo, source_sha = _source_repo(tmp_path)
    artifacts = generate_candidate(source_sha, tmp_path / "candidate", repo=repo)
    (artifacts.sandbox / "UNTRACKED-SENTINEL.txt").write_text("unexpected", encoding="utf-8")

    with pytest.raises(CandidateBoundaryError, match="sandbox file listing"):
        verify_candidate(artifacts.output_dir)

    (artifacts.sandbox / "UNTRACKED-SENTINEL.txt").unlink()
    (artifacts.sandbox / ".git").mkdir()
    (artifacts.sandbox / ".git" / "config").write_text("metadata", encoding="utf-8")
    with pytest.raises(CandidateBoundaryError, match="sandbox file listing"):
        verify_candidate(artifacts.output_dir)


@pytest.mark.parametrize(
    "source_sha",
    ["not-a-sha", "A" * 40, "0" * 40],
)
def test_generation_rejects_invalid_or_missing_source_sha(tmp_path: Path, source_sha: str) -> None:
    repo, _ = _source_repo(tmp_path)

    with pytest.raises(CandidateBoundaryError, match="source SHA|exact commit"):
        generate_candidate(source_sha, tmp_path / "candidate", repo=repo)

    assert not (tmp_path / "candidate").exists()


def test_generation_refuses_output_inside_repository(tmp_path: Path) -> None:
    repo, source_sha = _source_repo(tmp_path)

    with pytest.raises(CandidateBoundaryError, match="outside the Git repository"):
        generate_candidate(source_sha, repo / "candidate", repo=repo)


def test_cleanup_removes_only_complete_candidate_output(tmp_path: Path) -> None:
    repo, source_sha = _source_repo(tmp_path)
    output = tmp_path / "candidate"
    artifacts = generate_candidate(source_sha, output, repo=repo)

    cleanup_candidate(artifacts.output_dir)

    assert not output.exists()
