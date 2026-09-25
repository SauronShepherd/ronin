"""Safe backup and restore primitives for the reference SQLite deployment."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BackupManifest:
    """Portable identity manifest binding database and artifact digests."""

    database_sha256: str
    artifact_sha256: tuple[str, ...] = ()
    artifact_tree_sha256: str | None = None

    def __post_init__(self) -> None:
        if len(self.database_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in self.database_sha256
        ):
            raise ValueError("database_sha256 must be a lowercase SHA-256 digest")
        if tuple(sorted(set(self.artifact_sha256))) != self.artifact_sha256:
            raise ValueError("artifact digests must be sorted and unique")
        if any(
            len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
            for value in self.artifact_sha256
        ):
            raise ValueError("artifact_sha256 entries must be lowercase SHA-256 digests")
        if self.artifact_tree_sha256 is not None and (
            len(self.artifact_tree_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.artifact_tree_sha256)
        ):
            raise ValueError("artifact_tree_sha256 must be a lowercase SHA-256 digest")

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema": "ronin.backup-manifest/v2"
                if self.artifact_tree_sha256 is not None
                else "ronin.backup-manifest/v1",
                "database_sha256": self.database_sha256,
                "artifact_sha256": list(self.artifact_sha256),
                **(
                    {"artifact_tree_sha256": self.artifact_tree_sha256}
                    if self.artifact_tree_sha256 is not None
                    else {}
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, value: str) -> BackupManifest:
        payload = json.loads(value)
        if not isinstance(payload, dict) or payload.get("schema") not in {
            "ronin.backup-manifest/v1",
            "ronin.backup-manifest/v2",
        }:
            raise ValueError("unsupported backup manifest")
        artifacts = payload.get("artifact_sha256")
        if not isinstance(artifacts, list) or not all(isinstance(item, str) for item in artifacts):
            raise ValueError("artifact_sha256 must be a string array")
        tree_digest = payload.get("artifact_tree_sha256")
        if payload.get("schema") == "ronin.backup-manifest/v2" and not isinstance(tree_digest, str):
            raise ValueError("artifact_tree_sha256 must be a string")
        return cls(str(payload.get("database_sha256", "")), tuple(artifacts), tree_digest)


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_tree_sha256(root: Path) -> str:
    """Hash artifact paths and contents so logical identity cannot be swapped."""
    if not root.is_dir():
        raise FileNotFoundError(root)
    digest = hashlib.sha256()
    for path in sorted(path for path in root.rglob("*") if path.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def backup_sqlite(source: Path, destination: Path) -> Path:
    """Create a consistent SQLite backup and atomically publish it."""
    source = source.resolve()
    destination = destination.resolve()
    if source == destination:
        raise ValueError("backup destination must differ from source")
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with (
            closing(sqlite3.connect(source)) as source_db,
            closing(sqlite3.connect(temporary)) as target_db,
        ):
            source_db.backup(target_db)
            if target_db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("SQLite backup failed integrity check")
            target_db.commit()
        temporary.replace(destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def restore_sqlite(backup: Path, destination: Path) -> Path:
    """Restore a verified backup to a new or replaced SQLite database atomically."""
    backup = backup.resolve()
    destination = destination.resolve()
    if backup == destination:
        raise ValueError("restore destination must differ from backup")
    if not backup.is_file():
        raise FileNotFoundError(backup)
    with closing(sqlite3.connect(backup)) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise ValueError("SQLite backup failed integrity check")
    return backup_sqlite(backup, destination)


def backup_deployment(database: Path, artifacts: Path, destination: Path) -> Path:
    """Create a clean-directory backup containing SQLite, artifacts and manifest."""
    database = database.resolve()
    artifacts = artifacts.resolve()
    destination = destination.resolve()
    if not database.is_file() or not artifacts.is_dir():
        raise FileNotFoundError("database and artifacts directory are required")
    if destination.exists() or destination in {database, artifacts}:
        raise ValueError("backup destination must be a new directory")
    files = sorted(path for path in artifacts.rglob("*") if path.is_file())
    digests = tuple(sorted(sha256_file(path) for path in files))
    destination.mkdir(parents=True)
    try:
        backup_sqlite(database, destination / "database.sqlite")
        shutil.copytree(artifacts, destination / "artifacts")
        manifest = BackupManifest(
            sha256_file(destination / "database.sqlite"),
            digests,
            artifact_tree_sha256(destination / "artifacts"),
        )
        (destination / "manifest.json").write_text(manifest.to_json(), encoding="utf-8")
        return destination
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def restore_deployment(bundle: Path, database: Path, artifacts: Path) -> tuple[Path, Path]:
    """Restore a deployment bundle only after verifying all stored digests."""
    bundle = bundle.resolve()
    database = database.resolve()
    artifacts = artifacts.resolve()
    manifest_path = bundle / "manifest.json"
    backup = bundle / "database.sqlite"
    source_artifacts = bundle / "artifacts"
    if not manifest_path.is_file() or not backup.is_file() or not source_artifacts.is_dir():
        raise FileNotFoundError("invalid deployment backup bundle")
    manifest = BackupManifest.from_json(manifest_path.read_text(encoding="utf-8"))
    if sha256_file(backup) != manifest.database_sha256:
        raise ValueError("deployment database digest mismatch")
    files = sorted(path for path in source_artifacts.rglob("*") if path.is_file())
    if tuple(sorted(sha256_file(path) for path in files)) != manifest.artifact_sha256:
        raise ValueError("deployment artifact digest mismatch")
    if (
        manifest.artifact_tree_sha256 is not None
        and artifact_tree_sha256(source_artifacts) != manifest.artifact_tree_sha256
    ):
        raise ValueError("deployment artifact tree digest mismatch")
    if database.exists() or artifacts.exists():
        raise ValueError("restore destinations must be clean")
    database.parent.mkdir(parents=True, exist_ok=True)
    artifacts.parent.mkdir(parents=True, exist_ok=True)
    restore_sqlite(backup, database)
    shutil.copytree(source_artifacts, artifacts)
    return database, artifacts


__all__ = [
    "BackupManifest",
    "backup_deployment",
    "backup_sqlite",
    "artifact_tree_sha256",
    "restore_deployment",
    "restore_sqlite",
    "sha256_file",
]
