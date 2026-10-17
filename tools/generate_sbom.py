"""Generate candidate-bound, dependency-aware SBOM/provenance evidence.

The release job can run this without installing a third-party SBOM tool.  The
result is deliberately deterministic except for the builder timestamp, which
is recorded as metadata rather than included in the canonical digest.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
from pathlib import Path
from typing import Any

SCHEMA = "ronin.sbom-provenance/v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_revision(root: Path) -> str:
    try:
        return subprocess.check_output(  # noqa: S603, S607
            ["git", "-C", str(root), "rev-parse", "HEAD"],  # noqa: S607
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _dependencies() -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for distribution in sorted(
        importlib.metadata.distributions(), key=lambda item: item.metadata["Name"] or ""
    ):
        name = distribution.metadata["Name"]
        version = distribution.version
        if name and version:
            result.append({"name": name, "version": version})
    return result


def build_evidence(root: Path, artifacts: list[Path]) -> dict[str, Any]:
    resolved = [path.resolve() for path in artifacts]
    if not resolved or any(not path.is_file() for path in resolved):
        raise ValueError("all artifacts must exist and be files")
    names = [path.name for path in resolved]
    if len(names) != len(set(names)):
        raise ValueError("artifact file names must be unique")
    artifact_records = [
        {
            "name": path.name,
            "path": str(path),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in sorted(resolved, key=lambda item: item.name)
    ]
    evidence: dict[str, Any] = {
        "schema": SCHEMA,
        "source": {"revision": _git_revision(root.resolve())},
        "builder": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "tool": "tools.generate_sbom",
            "tool_version": "1",
        },
        "artifacts": artifact_records,
        "dependencies": _dependencies(),
    }
    canonical = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    evidence["evidence_sha256"] = hashlib.sha256(canonical).hexdigest()
    return evidence


def verify_evidence(path: Path, *, expected_revision: str | None = None) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("evidence must be a JSON object")
    if value.get("schema") != SCHEMA:
        raise ValueError("unsupported SBOM/provenance evidence schema")
    digest = value.pop("evidence_sha256", None)
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise ValueError("missing evidence_sha256")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != digest:
        raise ValueError("evidence_sha256 does not match canonical evidence")
    source = value.get("source")
    revision = source.get("revision") if isinstance(source, dict) else None
    if not isinstance(revision, str) or not revision.strip():
        raise ValueError("evidence source revision is missing")
    if expected_revision is not None and (revision == "unknown" or revision != expected_revision):
        raise ValueError(
            f"evidence source revision {revision!r} does not match expected revision "
            f"{expected_revision!r}"
        )
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("evidence must contain artifacts")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError("artifact record must be an object")
        artifact_path_value = artifact.get("path")
        digest_value = artifact.get("sha256")
        size = artifact.get("bytes")
        if (
            not isinstance(artifact_path_value, str)
            or not isinstance(digest_value, str)
            or not _SHA256.fullmatch(digest_value)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
        ):
            raise ValueError("artifact record has invalid path, digest, or size")
        artifact_path = Path(artifact_path_value)
        if (
            not artifact_path.is_file()
            or artifact_path.stat().st_size != size
            or _sha256(artifact_path) != digest_value
        ):
            raise ValueError(f"artifact digest mismatch: {artifact.get('name', '<unknown>')}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="generate-sbom")
    parser.add_argument("artifacts", nargs="+", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument(
        "--expected-commit",
        help="require verified evidence to target this exact source revision",
    )
    args = parser.parse_args()
    if args.verify:
        verify_evidence(args.output, expected_revision=args.expected_commit)
    else:
        args.output.write_text(
            json.dumps(build_evidence(args.root, args.artifacts), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
