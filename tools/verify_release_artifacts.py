"""Verify release-evidence artifact bytes inside an explicit sandbox root."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from tools.release_evidence import EvidenceError


def _relative_artifact_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError("artifact path must be a non-empty string")
    raw_parts = value.replace("\\", "/").split("/")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in raw_parts or "." in raw_parts:
        raise EvidenceError(f"artifact path is not confined to the sandbox root: {value}")
    if not path.parts:
        raise EvidenceError("artifact path is empty")
    return path


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(bundle: dict[str, Any], root: Path) -> dict[str, Any]:
    """Re-hash every declared artifact, refusing escapes and symlink traversal."""

    validated = load_bundle(bundle)
    sandbox = root.expanduser().resolve()
    if not sandbox.is_dir():
        raise EvidenceError(f"artifact root is not a directory: {root}")
    checked: list[dict[str, Any]] = []
    for record in validated["records"]:
        if record["status"] not in {"passed", "failed"}:
            continue
        digests = record["artifact_digests"]
        for declared, expected in digests.items():
            relative = _relative_artifact_path(declared)
            candidate = sandbox.joinpath(*relative.parts)
            try:
                candidate.relative_to(sandbox)
            except ValueError as exc:  # defensive against platform path semantics
                raise EvidenceError(f"artifact path escapes the sandbox root: {declared}") from exc
            current = sandbox
            for part in relative.parts:
                current = current / part
                if current.is_symlink():
                    raise EvidenceError(f"artifact path contains a symlink: {declared}")
            if not candidate.is_file():
                raise EvidenceError(f"artifact is missing or not a regular file: {declared}")
            actual = _digest(candidate)
            if actual != expected:
                raise EvidenceError(f"artifact digest mismatch: {declared}")
            checked.append({"gate_id": record["gate_id"], "path": declared, "sha256": actual})
    return {
        "schema": "ronin.release-artifact-verification/v1",
        "root": str(sandbox),
        "artifacts": checked,
    }


def load_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Validate an in-memory bundle without allowing a caller to bypass schema checks."""

    # ``load`` owns the canonical validation, but accepts a path. Reuse its
    # validator through a private temporary-free equivalent to keep this tool
    # deterministic and avoid writing the caller's bundle.
    from tools.release_evidence import validate_bundle

    return validate_bundle(bundle)


def main() -> int:
    parser = argparse.ArgumentParser(prog="verify-release-artifacts")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    try:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        result = verify(bundle, args.root)
    except (OSError, json.JSONDecodeError, EvidenceError) as exc:
        print(f"release artifacts invalid: {exc}")
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
