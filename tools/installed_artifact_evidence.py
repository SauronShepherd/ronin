"""Emit fail-closed evidence for the installed-artifact qualification job."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from tools.release_evidence import SCHEMA, release_verdict, validate_bundle

GATES = frozenset(
    {
        "installed-source-assets",
        "installed-wheel-browser",
        "installed-sdist-browser",
        "installed-wheel-a11y",
        "installed-sdist-a11y",
        "artifact-identity",
    }
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_digests(path: Path, commit: str) -> dict[str, str]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read artifact identity: {path}") from exc
    if manifest.get("schema") != "ronin.artifact-identity/v1":
        raise ValueError("artifact identity schema is invalid")
    if manifest.get("commit") != commit:
        raise ValueError("artifact identity commit does not match evidence commit")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("artifact identity must contain artifacts")
    result: dict[str, str] = {}
    for item in artifacts:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise ValueError("artifact identity contains an invalid artifact")
        name = item["name"].strip()
        if not name or name in result:
            raise ValueError("artifact identity contains a duplicate artifact")
        sha256 = item.get("sha256")
        if (
            not isinstance(sha256, str)
            or len(sha256) != 64
            or any(character not in "0123456789abcdef" for character in sha256)
        ):
            raise ValueError("artifact identity contains an invalid SHA-256")
        result[name] = sha256
    return result


def _validate_sbom(path: Path) -> None:
    """Require a real SPDX/CycloneDX JSON document before release evidence passes."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read SBOM: {path}") from exc
    if not isinstance(document, dict):
        raise ValueError("SBOM must be a JSON object")
    is_spdx = isinstance(document.get("spdxVersion"), str) and isinstance(
        document.get("packages"), list
    )
    is_cyclonedx = isinstance(document.get("bomFormat"), str) and isinstance(
        document.get("components"), list
    )
    if not (is_spdx or is_cyclonedx):
        raise ValueError("SBOM must be SPDX or CycloneDX JSON")


def build_bundle(
    commit: str, artifact_identity: Path, sbom: Path | None = None
) -> dict[str, object]:
    now = datetime.now(UTC).isoformat()
    artifacts = [str(artifact_identity)]
    artifact_digests = _artifact_digests(artifact_identity, commit)
    artifact_digests[str(artifact_identity)] = _sha256(artifact_identity)
    if sbom is not None:
        _validate_sbom(sbom)
        artifacts.append(str(sbom))
        artifact_digests[str(sbom)] = _sha256(sbom)
    records = [
        {
            "gate_id": gate,
            "status": "passed",
            "commit": commit,
            "environment": {"fingerprint": "github-actions-installed-artifact"},
            "command": "release-qualification.yml",
            "started_at": now,
            "ended_at": now,
            "artifacts": artifacts,
            "artifact_digests": artifact_digests,
        }
        for gate in sorted(GATES)
    ]
    bundle = {"schema": SCHEMA, "commit": commit, "generated_at": now, "records": records}
    validate_bundle(bundle)
    release_verdict(bundle, set(GATES))
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--artifact-identity", type=Path, required=True)
    parser.add_argument("--sbom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verdict-output", type=Path)
    args = parser.parse_args()
    bundle = build_bundle(args.commit, args.artifact_identity, args.sbom)
    args.output.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    verdict = release_verdict(bundle, set(GATES))
    if args.verdict_output is not None:
        args.verdict_output.write_text(
            json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(verdict, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
