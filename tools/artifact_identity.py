"""Create candidate-bound artifact identity evidence for release qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = "ronin.artifact-identity/v1"


def git_commit() -> str:
    return subprocess.run(  # noqa: S603, S607 - fixed git command
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def digest(path: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            hasher.update(chunk)
    return hasher.hexdigest(), size


def build_manifest(paths: list[Path], *, commit: str) -> dict[str, object]:
    if not commit or not commit.strip():
        raise ValueError("commit must be non-empty")
    artifacts = []
    for path in sorted(paths, key=lambda item: item.name):
        if not path.is_file():
            raise FileNotFoundError(path)
        sha256, size = digest(path)
        if path.suffix == ".whl":
            kind = "wheel"
        elif path.name.endswith(".tar.gz"):
            kind = "sdist"
        elif path.suffix in {".json", ".txt"}:
            kind = "evidence"
        else:
            kind = "other"
        artifacts.append({"name": path.name, "kind": kind, "sha256": sha256, "size": size})
    if not artifacts:
        raise ValueError("at least one artifact is required")
    return {
        "schema": SCHEMA,
        "commit": commit,
        "generated_at": datetime.now(UTC).isoformat(),
        "artifacts": artifacts,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifacts", nargs="+", type=Path)
    parser.add_argument("--commit", default=None)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest = build_manifest(args.artifacts, commit=args.commit or git_commit())
    rendered = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
