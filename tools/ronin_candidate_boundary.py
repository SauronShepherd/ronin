"""Build and verify a reproducible candidate boundary from an exact Git commit.

The candidate is deliberately independent from the working tree.  Generation
uses ``git archive`` and records only deterministic facts about that archive;
verification can then run from the extracted sandbox without Git metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO

SCHEMA = "ronin.candidate-boundary/v1"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_ARCHIVE_RE = re.compile(r"^candidate-(?P<sha>[0-9a-f]{40})\.tar$")
_MANIFEST_RE = re.compile(r"^candidate-(?P<sha>[0-9a-f]{40})\.manifest\.json$")
_DIGEST_FILE_RE = re.compile(r"^candidate-(?P<sha>[0-9a-f]{40})\.sha256$")
_CHUNK_SIZE = 1024 * 1024


class CandidateBoundaryError(RuntimeError):
    """Raised when candidate identity or boundary verification fails closed."""


@dataclass(frozen=True, slots=True)
class CandidateArtifacts:
    """Paths emitted for one candidate boundary."""

    source_sha: str
    output_dir: Path
    archive: Path
    manifest: Path
    digest_file: Path
    sandbox: Path


@dataclass(frozen=True, slots=True)
class CandidateVerification:
    """Verified candidate facts suitable for a receipt."""

    source_sha: str
    archive_sha256: str
    manifest_sha256: str
    file_count: int
    total_bytes: int


@dataclass(frozen=True, slots=True)
class _FileEntry:
    path: str
    mode: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class _ArchiveSnapshot:
    files: tuple[_FileEntry, ...]
    directories: tuple[str, ...]


def _canonical_json(payload: object) -> bytes:
    try:
        rendered = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise CandidateBoundaryError(f"manifest cannot be canonicalized: {exc}") from exc
    return (rendered + "\n").encode("utf-8")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, child in pairs:
        if key in value:
            raise CandidateBoundaryError(f"manifest contains duplicate key: {key}")
        value[key] = child
    return value


def _reject_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON value: {value}")


def _decode_json(payload: bytes, *, label: str) -> object:
    try:
        return json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise CandidateBoundaryError(f"{label} is not valid JSON: {exc}") from exc


def _run_git(repo: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(  # noqa: S603, S607 - Git arguments are fixed by this tool
            ["git", "-C", str(repo), *args],  # noqa: S607
            check=False,
            capture_output=True,
        )  # noqa: S603, S607 - Git arguments are fixed by this tool
    except OSError as exc:
        raise CandidateBoundaryError(f"cannot execute Git: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise CandidateBoundaryError(
            f"Git command failed ({' '.join(args)}): {detail or 'no diagnostic'}"
        )
    return result.stdout


def _validate_source_sha(source_sha: str) -> str:
    if not isinstance(source_sha, str) or _SHA_RE.fullmatch(source_sha) is None:
        raise CandidateBoundaryError(
            "source SHA must be an exact lowercase 40-character commit SHA"
        )
    return source_sha


def _repo_root(repo: Path) -> Path:
    candidate = repo.expanduser().resolve()
    if not candidate.is_dir():
        raise CandidateBoundaryError(f"repository directory does not exist: {candidate}")
    raw = _run_git(candidate, "rev-parse", "--show-toplevel").strip()
    if not raw:
        raise CandidateBoundaryError("Git did not return a repository root")
    return Path(raw.decode("utf-8", errors="strict")).resolve()


def _resolve_commit(repo: Path, source_sha: str) -> None:
    try:
        resolved = _run_git(repo, "rev-parse", "--verify", "--quiet", f"{source_sha}^{{commit}}")
    except CandidateBoundaryError as exc:
        raise CandidateBoundaryError(
            f"source SHA is not an existing exact commit: {source_sha}"
        ) from exc
    resolved_sha = resolved.decode("ascii", errors="replace").strip()
    if resolved_sha != source_sha:
        raise CandidateBoundaryError(f"source SHA is not an existing exact commit: {source_sha}")


def _tracked_tree(repo: Path, source_sha: str) -> dict[str, str]:
    raw = _run_git(repo, "ls-tree", "-r", "-z", "-l", "--full-tree", source_sha)
    tracked: dict[str, str] = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            header, path_bytes = record.split(b"\t", 1)
            mode_bytes, kind, _object_id, _size = header.split(b" ", 3)
            path = path_bytes.decode("utf-8", errors="strict")
            mode = mode_bytes.decode("ascii")
        except (ValueError, UnicodeDecodeError) as exc:
            raise CandidateBoundaryError("Git returned an unreadable tree entry") from exc
        if kind != b"blob" or mode not in {"100644", "100755"}:
            raise CandidateBoundaryError(f"candidate contains unsupported tracked entry: {path!r}")
        if not path or path in tracked:
            raise CandidateBoundaryError("Git tree contains an invalid or duplicate path")
        tracked[path] = mode
    return tracked


def _safe_relative_path(raw_name: str, *, label: str) -> str:
    if not isinstance(raw_name, str) or not raw_name or "\\" in raw_name:
        raise CandidateBoundaryError(f"{label} contains an unsafe path: {raw_name!r}")
    normalized = raw_name.rstrip("/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or ":" in path.parts[0]
    ):
        raise CandidateBoundaryError(f"{label} contains an unsafe path: {raw_name!r}")
    value = path.as_posix()
    if value == "." or value == ".git" or value.startswith(".git/"):
        raise CandidateBoundaryError(f"{label} must not contain Git metadata: {raw_name!r}")
    return value


def _hash_stream(stream: IO[bytes]) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: stream.read(_CHUNK_SIZE), b""):
        size += len(chunk)
        hasher.update(chunk)
    return hasher.hexdigest(), size


def _hash_file(path: Path) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        raise CandidateBoundaryError(f"expected a regular file: {path}")
    try:
        with path.open("rb") as stream:
            return _hash_stream(stream)
    except OSError as exc:
        raise CandidateBoundaryError(f"cannot read file {path}: {exc}") from exc


def _archive_snapshot(archive: Path) -> _ArchiveSnapshot:
    if archive.is_symlink() or not archive.is_file():
        raise CandidateBoundaryError(f"archive is missing or not a regular file: {archive}")
    files: dict[str, _FileEntry] = {}
    directories: set[str] = set()
    try:
        with tarfile.open(archive, mode="r:") as handle:
            for member in handle.getmembers():
                name = _safe_relative_path(member.name, label="archive")
                if member.isdir():
                    directories.add(name)
                    continue
                if not member.isfile():
                    raise CandidateBoundaryError(
                        f"archive contains unsupported member type: {member.name!r}"
                    )
                if name in files:
                    raise CandidateBoundaryError(f"archive contains duplicate file: {name}")
                stream = handle.extractfile(member)
                if stream is None:
                    raise CandidateBoundaryError(f"archive member is unreadable: {name}")
                with stream:
                    digest, size = _hash_stream(stream)
                if size != member.size:
                    raise CandidateBoundaryError(
                        f"archive member size changed while reading: {name}"
                    )
                mode = "100755" if member.mode & 0o111 else "100644"
                files[name] = _FileEntry(name, mode, size, digest)
    except CandidateBoundaryError:
        raise
    except (OSError, tarfile.TarError) as exc:
        raise CandidateBoundaryError(f"cannot read candidate archive: {archive}: {exc}") from exc
    return _ArchiveSnapshot(
        files=tuple(sorted(files.values(), key=lambda item: item.path)),
        directories=tuple(sorted(directories)),
    )


def _parent_directories(paths: Iterable[str]) -> set[str]:
    directories: set[str] = set()
    for raw_path in paths:
        path = PurePosixPath(raw_path)
        for index in range(1, len(path.parts)):
            directories.add(PurePosixPath(*path.parts[:index]).as_posix())
    return directories


def _manifest_payload(
    source_sha: str,
    archive: Path,
    archive_sha256: str,
    archive_size: int,
    files: tuple[_FileEntry, ...],
) -> dict[str, object]:
    return {
        "archive": {
            "filename": archive.name,
            "format": "tar",
            "sha256": archive_sha256,
            "size": archive_size,
        },
        "file_count": len(files),
        "files": [
            {
                "mode": entry.mode,
                "path": entry.path,
                "sha256": entry.sha256,
                "size": entry.size,
            }
            for entry in files
        ],
        "schema": SCHEMA,
        "source_sha": source_sha,
        "total_bytes": sum(entry.size for entry in files),
    }


def _validate_digest(value: object, *, label: str) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise CandidateBoundaryError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _validate_manifest_payload(
    payload: object, *, archive_name: str, manifest_name: str
) -> tuple[str, str, int, tuple[_FileEntry, ...], int]:
    if not isinstance(payload, dict):
        raise CandidateBoundaryError("manifest root must be an object")
    expected_keys = {"archive", "file_count", "files", "schema", "source_sha", "total_bytes"}
    if set(payload) != expected_keys:
        raise CandidateBoundaryError("manifest keys do not match the candidate contract")
    if payload["schema"] != SCHEMA:
        raise CandidateBoundaryError("manifest schema is unsupported")
    source_sha = _validate_source_sha(payload["source_sha"])
    expected_archive_name = f"candidate-{source_sha}.tar"
    expected_manifest_name = f"candidate-{source_sha}.manifest.json"
    if archive_name != expected_archive_name or manifest_name != expected_manifest_name:
        raise CandidateBoundaryError("candidate filenames do not bind to source SHA")

    archive = payload["archive"]
    if not isinstance(archive, dict) or set(archive) != {"filename", "format", "sha256", "size"}:
        raise CandidateBoundaryError("manifest archive identity is malformed")
    if archive["filename"] != archive_name or archive["format"] != "tar":
        raise CandidateBoundaryError("manifest archive identity does not match its files")
    archive_sha256 = _validate_digest(archive["sha256"], label="archive sha256")
    archive_size = archive["size"]
    if isinstance(archive_size, bool) or not isinstance(archive_size, int) or archive_size < 0:
        raise CandidateBoundaryError("archive size must be a non-negative integer")

    file_count = payload["file_count"]
    total_bytes = payload["total_bytes"]
    if isinstance(file_count, bool) or not isinstance(file_count, int) or file_count < 0:
        raise CandidateBoundaryError("file_count must be a non-negative integer")
    if isinstance(total_bytes, bool) or not isinstance(total_bytes, int) or total_bytes < 0:
        raise CandidateBoundaryError("total_bytes must be a non-negative integer")

    raw_files = payload["files"]
    if not isinstance(raw_files, list):
        raise CandidateBoundaryError("manifest files must be a list")
    entries: list[_FileEntry] = []
    for raw_entry in raw_files:
        if not isinstance(raw_entry, dict) or set(raw_entry) != {"mode", "path", "sha256", "size"}:
            raise CandidateBoundaryError("manifest file entry is malformed")
        path = _safe_relative_path(raw_entry["path"], label="manifest")
        if raw_entry["path"] != path:
            raise CandidateBoundaryError("manifest paths must use normalized POSIX form")
        mode = raw_entry["mode"]
        if mode not in {"100644", "100755"}:
            raise CandidateBoundaryError(f"manifest mode is unsupported for {path}")
        size = raw_entry["size"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise CandidateBoundaryError(f"manifest size is invalid for {path}")
        digest = _validate_digest(raw_entry["sha256"], label=f"manifest sha256 for {path}")
        entries.append(_FileEntry(path, mode, size, digest))
    files = tuple(entries)
    if files != tuple(sorted(files, key=lambda item: item.path)):
        raise CandidateBoundaryError("manifest file list is not sorted")
    if len({entry.path for entry in files}) != len(files):
        raise CandidateBoundaryError("manifest file list contains duplicate paths")
    if file_count != len(files):
        raise CandidateBoundaryError("manifest file_count does not match file list")
    if total_bytes != sum(entry.size for entry in files):
        raise CandidateBoundaryError("manifest total_bytes does not match file list")
    return source_sha, archive_sha256, archive_size, files, total_bytes


def _load_manifest(path: Path, *, archive_name: str) -> tuple[dict[str, object], str]:
    if path.is_symlink() or not path.is_file():
        raise CandidateBoundaryError(f"manifest is missing or not a regular file: {path}")
    raw = path.read_bytes()
    payload = _decode_json(raw, label="manifest")
    if not isinstance(payload, dict):
        raise CandidateBoundaryError("manifest root must be an object")
    canonical = _canonical_json(payload)
    if raw != canonical:
        raise CandidateBoundaryError("manifest is not canonical or was modified")
    _validate_manifest_payload(payload, archive_name=archive_name, manifest_name=path.name)
    return payload, hashlib.sha256(raw).hexdigest()


def _discover(output_dir: Path) -> CandidateArtifacts:
    output = output_dir.expanduser().resolve()
    if output.is_symlink() or not output.is_dir():
        raise CandidateBoundaryError(f"candidate output directory is missing: {output}")
    names = {item.name for item in output.iterdir()}
    archives = [item for item in output.iterdir() if _ARCHIVE_RE.fullmatch(item.name)]
    manifests = [item for item in output.iterdir() if _MANIFEST_RE.fullmatch(item.name)]
    digest_files = [item for item in output.iterdir() if _DIGEST_FILE_RE.fullmatch(item.name)]
    sandbox = output / "sandbox"
    if len(archives) != 1 or len(manifests) != 1 or len(digest_files) != 1:
        raise CandidateBoundaryError(
            "candidate output must contain one archive, manifest, and digest"
        )
    if digest_files[0].is_symlink() or not digest_files[0].is_file():
        raise CandidateBoundaryError("candidate digest file is missing or not a regular file")
    if sandbox.is_symlink() or not sandbox.is_dir():
        raise CandidateBoundaryError("candidate output must contain a sandbox directory")
    expected_names = {
        archives[0].name,
        manifests[0].name,
        digest_files[0].name,
        "sandbox",
    }
    if names != expected_names:
        extras = sorted(names - expected_names)
        raise CandidateBoundaryError(f"candidate output contains unexpected entries: {extras}")
    sha_values = {
        _ARCHIVE_RE.fullmatch(archives[0].name).group("sha"),  # type: ignore[union-attr]
        _MANIFEST_RE.fullmatch(manifests[0].name).group("sha"),  # type: ignore[union-attr]
        _DIGEST_FILE_RE.fullmatch(digest_files[0].name).group("sha"),  # type: ignore[union-attr]
    }
    if len(sha_values) != 1:
        raise CandidateBoundaryError("candidate artifact filenames do not share one SHA")
    source_sha = next(iter(sha_values))
    return CandidateArtifacts(
        source_sha=source_sha,
        output_dir=output,
        archive=archives[0],
        manifest=manifests[0],
        digest_file=digest_files[0],
        sandbox=sandbox,
    )


def _verify_sandbox(sandbox: Path, files: tuple[_FileEntry, ...]) -> None:
    expected = {entry.path: entry for entry in files}
    actual_files: dict[str, Path] = {}
    actual_directories: set[str] = set()
    for sandbox_path in sandbox.rglob("*"):
        relative = sandbox_path.relative_to(sandbox).as_posix()
        if sandbox_path.is_symlink():
            raise CandidateBoundaryError(f"sandbox contains a symlink: {relative}")
        if sandbox_path.is_dir():
            actual_directories.add(relative)
        elif sandbox_path.is_file():
            if relative in actual_files:
                raise CandidateBoundaryError(f"sandbox contains duplicate path: {relative}")
            actual_files[relative] = sandbox_path
        else:
            raise CandidateBoundaryError(f"sandbox contains unsupported entry: {relative}")
    if set(actual_files) != set(expected):
        missing = sorted(set(expected) - set(actual_files))
        extra = sorted(set(actual_files) - set(expected))
        raise CandidateBoundaryError(
            f"sandbox file listing does not match manifest; missing={missing}, extra={extra}"
        )
    expected_directories = _parent_directories(expected)
    if actual_directories != expected_directories:
        missing = sorted(expected_directories - actual_directories)
        extra = sorted(actual_directories - expected_directories)
        raise CandidateBoundaryError(
            f"sandbox directory listing does not match manifest; missing={missing}, extra={extra}"
        )
    for relative, expected_entry in expected.items():
        digest, size = _hash_file(actual_files[relative])
        if size != expected_entry.size or digest != expected_entry.sha256:
            raise CandidateBoundaryError(f"sandbox file does not match manifest: {relative}")


def _verify_source(
    repo: Path, source_sha: str, manifest_files: tuple[_FileEntry, ...], archive: Path
) -> None:
    _resolve_commit(repo, source_sha)
    tracked = _tracked_tree(repo, source_sha)
    observed = {entry.path: entry.mode for entry in manifest_files}
    if observed != tracked:
        missing = sorted(set(tracked) - set(observed))
        extra = sorted(set(observed) - set(tracked))
        raise CandidateBoundaryError(
            f"manifest does not match exact Git tree; missing={missing}, extra={extra}"
        )
    try:
        with tempfile.TemporaryDirectory(prefix="ronin-candidate-verify-") as temporary:
            expected_archive = Path(temporary) / archive.name
            _run_git(
                repo,
                "archive",
                "--format=tar",
                f"--output={expected_archive}",
                source_sha,
            )
            expected_digest, expected_size = _hash_file(expected_archive)
            actual_digest, actual_size = _hash_file(archive)
            if (actual_digest, actual_size) != (expected_digest, expected_size):
                raise CandidateBoundaryError(
                    "archive does not match a fresh git archive of the source SHA"
                )
    except OSError as exc:
        raise CandidateBoundaryError(f"cannot verify source archive: {exc}") from exc


def verify_candidate(output_dir: Path, *, repo: Path | None = None) -> CandidateVerification:
    """Verify candidate files, archive contents, sandbox contents, and optional Git source."""

    artifacts = _discover(output_dir)
    payload, manifest_sha256 = _load_manifest(
        artifacts.manifest, archive_name=artifacts.archive.name
    )
    source_sha, archive_sha256, archive_size, files, total_bytes = _validate_manifest_payload(
        payload, archive_name=artifacts.archive.name, manifest_name=artifacts.manifest.name
    )
    if source_sha != artifacts.source_sha:
        raise CandidateBoundaryError("manifest source SHA does not match artifact filenames")
    actual_archive_sha256, actual_archive_size = _hash_file(artifacts.archive)
    if (actual_archive_sha256, actual_archive_size) != (archive_sha256, archive_size):
        raise CandidateBoundaryError("archive digest or size does not match manifest")
    expected_digest_file = (
        f"{archive_sha256}  {artifacts.archive.name}\n"
        f"{manifest_sha256}  {artifacts.manifest.name}\n"
    ).encode("ascii")
    if artifacts.digest_file.read_bytes() != expected_digest_file:
        raise CandidateBoundaryError("candidate digest file does not match archive and manifest")

    snapshot = _archive_snapshot(artifacts.archive)
    if snapshot.files != files:
        raise CandidateBoundaryError("archive file listing or file hashes do not match manifest")
    _verify_sandbox(artifacts.sandbox, files)
    if repo is not None:
        repo_root = _repo_root(repo)
        _verify_source(repo_root, source_sha, files, artifacts.archive)
    return CandidateVerification(
        source_sha=source_sha,
        archive_sha256=archive_sha256,
        manifest_sha256=manifest_sha256,
        file_count=len(files),
        total_bytes=total_bytes,
    )


def _ensure_outside_repo(output_dir: Path, repo_root: Path) -> None:
    try:
        output_dir.relative_to(repo_root)
    except ValueError:
        return
    raise CandidateBoundaryError("candidate output must live outside the Git repository")


def _extract_archive(archive: Path, sandbox: Path) -> None:
    if sandbox.exists():
        raise CandidateBoundaryError(f"sandbox already exists: {sandbox}")
    sandbox.mkdir()
    try:
        with tarfile.open(archive, mode="r:") as handle:
            for member in handle.getmembers():
                relative = _safe_relative_path(member.name, label="archive")
                target = sandbox.joinpath(*PurePosixPath(relative).parts)
                try:
                    target.relative_to(sandbox)
                except ValueError as exc:
                    raise CandidateBoundaryError(f"archive escapes sandbox: {relative}") from exc
                if member.isdir():
                    if target.exists() and not target.is_dir():
                        raise CandidateBoundaryError(f"archive path collision: {relative}")
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    raise CandidateBoundaryError(f"archive contains unsupported member: {relative}")
                if target.exists() or target.is_symlink():
                    raise CandidateBoundaryError(f"archive contains duplicate path: {relative}")
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = handle.extractfile(member)
                if stream is None:
                    raise CandidateBoundaryError(f"archive member is unreadable: {relative}")
                with stream, target.open("xb") as destination:
                    shutil.copyfileobj(stream, destination, length=_CHUNK_SIZE)
    except CandidateBoundaryError:
        raise
    except (OSError, tarfile.TarError) as exc:
        raise CandidateBoundaryError(f"cannot extract candidate archive: {exc}") from exc


def generate_candidate(
    source_sha: str, output_dir: Path, *, repo: Path | None = None
) -> CandidateArtifacts:
    """Create a candidate archive, manifest, digest binding, and clean sandbox."""

    source_sha = _validate_source_sha(source_sha)
    repo_root = _repo_root(repo or Path.cwd())
    _resolve_commit(repo_root, source_sha)
    output = output_dir.expanduser().resolve()
    _ensure_outside_repo(output, repo_root)
    if output.exists():
        raise CandidateBoundaryError(f"candidate output directory already exists: {output}")
    output.mkdir(parents=True)
    archive = output / f"candidate-{source_sha}.tar"
    manifest = output / f"candidate-{source_sha}.manifest.json"
    digest_file = output / f"candidate-{source_sha}.sha256"
    sandbox = output / "sandbox"
    artifacts = CandidateArtifacts(source_sha, output, archive, manifest, digest_file, sandbox)
    try:
        _run_git(
            repo_root,
            "archive",
            "--format=tar",
            f"--output={archive}",
            source_sha,
        )
        tracked = _tracked_tree(repo_root, source_sha)
        snapshot = _archive_snapshot(archive)
        observed = {entry.path: entry.mode for entry in snapshot.files}
        if observed != tracked:
            missing = sorted(set(tracked) - set(observed))
            extra = sorted(set(observed) - set(tracked))
            raise CandidateBoundaryError(
                "git archive file listing does not match source tree; "
                f"missing={missing}, extra={extra}"
            )
        archive_sha256, archive_size = _hash_file(archive)
        payload = _manifest_payload(
            source_sha, archive, archive_sha256, archive_size, snapshot.files
        )
        manifest.write_bytes(_canonical_json(payload))
        manifest_sha256, _ = _hash_file(manifest)
        digest_file.write_bytes(
            f"{archive_sha256}  {archive.name}\n{manifest_sha256}  {manifest.name}\n".encode(
                "ascii"
            )
        )
        _extract_archive(archive, sandbox)
        verify_candidate(output, repo=repo_root)
        return artifacts
    except Exception:
        if output.exists():
            shutil.rmtree(output)
        raise


def cleanup_candidate(output_dir: Path) -> None:
    """Remove exactly one complete candidate output directory after validation."""

    artifacts = _discover(output_dir)
    output = artifacts.output_dir
    if output.parent == output or output == Path(output.anchor):
        raise CandidateBoundaryError("refusing to clean a filesystem root")
    try:
        shutil.rmtree(output)
    except OSError as exc:
        raise CandidateBoundaryError(f"candidate cleanup failed: {exc}") from exc
    if output.exists():
        raise CandidateBoundaryError(f"candidate cleanup left artifacts: {output}")


def _summary(artifacts: CandidateArtifacts, verification: CandidateVerification) -> str:
    return json.dumps(
        {
            "archive": str(artifacts.archive),
            "archive_sha256": verification.archive_sha256,
            "file_count": verification.file_count,
            "manifest": str(artifacts.manifest),
            "manifest_sha256": verification.manifest_sha256,
            "sandbox": str(artifacts.sandbox),
            "source_sha": verification.source_sha,
            "total_bytes": verification.total_bytes,
        },
        sort_keys=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    generate_parser = commands.add_parser("generate", help="generate and verify a candidate")
    generate_parser.add_argument(
        "--sha", required=True, help="exact lowercase 40-character commit SHA"
    )
    generate_parser.add_argument("--repo", type=Path, default=Path.cwd())
    generate_parser.add_argument("--output-dir", type=Path, required=True)

    verify_parser = commands.add_parser("verify", help="verify a candidate output directory")
    verify_parser.add_argument("--output-dir", type=Path, required=True)
    verify_parser.add_argument("--repo", type=Path)

    cleanup_parser = commands.add_parser(
        "cleanup", help="remove a complete candidate output directory"
    )
    cleanup_parser.add_argument("--output-dir", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            artifacts = generate_candidate(args.sha, args.output_dir, repo=args.repo)
            verification = verify_candidate(artifacts.output_dir, repo=args.repo)
            print(_summary(artifacts, verification))
        elif args.command == "verify":
            artifacts = _discover(args.output_dir)
            verification = verify_candidate(args.output_dir, repo=args.repo)
            print(_summary(artifacts, verification))
        else:
            cleanup_candidate(args.output_dir)
            print(f"cleaned {Path(args.output_dir).expanduser().resolve()}")
    except (CandidateBoundaryError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
