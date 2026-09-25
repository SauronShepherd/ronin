"""Backup and restore the PostgreSQL service of the Ronin appliance."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value or value != value.strip():
        raise ValueError(f"{name} must be set to a non-empty trimmed value")
    return value


def _compose_prefix(compose_file: Path) -> list[str]:
    return ["docker", "compose", "-f", str(compose_file)]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checksum_path(source: Path) -> Path:
    return source.with_name(f"{source.name}.sha256")


def backup(compose_file: Path, output: Path) -> None:
    if output.exists() and output.is_dir():
        raise ValueError("backup output must be a file")
    output.parent.mkdir(parents=True, exist_ok=True)
    user = os.environ.get("POSTGRES_USER", "ronin").strip() or "ronin"
    database = os.environ.get("POSTGRES_DB", "ronin").strip() or "ronin"
    command = _compose_prefix(compose_file) + [
        "exec",
        "-T",
        "postgres",
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--username",
        user,
        database,
    ]
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with temporary.open("wb") as stream:
            subprocess.run(command, check=True, stdout=stream)  # noqa: S603
        digest = _sha256(temporary)
        temporary.replace(output)
        _checksum_path(output).write_text(f"{digest}  {output.name}\n", encoding="ascii")
    finally:
        temporary.unlink(missing_ok=True)


def restore(compose_file: Path, source: Path, *, force: bool) -> None:
    if not source.is_file():
        raise ValueError("restore source must be an existing file")
    checksum = _checksum_path(source)
    if checksum.is_file():
        expected = checksum.read_text(encoding="ascii").strip().split()
        if (
            len(expected) != 2
            or expected[1] != source.name
            or len(expected[0]) != 64
            or any(character not in "0123456789abcdefABCDEF" for character in expected[0])
        ):
            raise ValueError("invalid PostgreSQL backup checksum sidecar")
        if _sha256(source) != expected[0]:
            raise ValueError("PostgreSQL backup checksum mismatch")
    if not force:
        raise ValueError("restore is destructive; pass --force explicitly")
    user = os.environ.get("POSTGRES_USER", "ronin").strip() or "ronin"
    database = os.environ.get("POSTGRES_DB", "ronin").strip() or "ronin"
    command = _compose_prefix(compose_file) + [
        "exec",
        "-T",
        "postgres",
        "pg_restore",
        "--clean",
        "--if-exists",
        "--no-owner",
        "--username",
        user,
        "--dbname",
        database,
    ]
    with source.open("rb") as stream:
        subprocess.run(command, check=True, stdin=stream)  # noqa: S603


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-file", type=Path, default=Path("compose.yaml"))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--backup", type=Path, metavar="FILE")
    mode.add_argument("--restore", type=Path, metavar="FILE")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    _required_env("RONIN_TOKEN")
    _required_env("RONIN_RUNNER_BROKER_TOKEN")
    if args.backup is not None:
        backup(args.compose_file, args.backup)
    else:
        restore(args.compose_file, args.restore, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
