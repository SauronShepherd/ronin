"""Fail-closed validation for candidate-bound release supply-chain evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


class SupplyChainEvidenceError(ValueError):
    """Raised when supply-chain evidence cannot bind to one candidate."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SupplyChainEvidenceError(f"cannot read JSON evidence: {path}") from exc
    if not isinstance(value, dict):
        raise SupplyChainEvidenceError(f"evidence must be an object: {path}")
    return value


def validate(
    *,
    commit: str,
    artifact_identity: Path,
    sboms: list[Path],
    provenance: Path | None = None,
) -> dict[str, Any]:
    """Validate exact candidate identity, typed SBOMs, and optional provenance."""
    if not commit.strip():
        raise SupplyChainEvidenceError("commit must be non-empty")
    identity = _load(artifact_identity)
    if identity.get("commit") != commit:
        raise SupplyChainEvidenceError("artifact identity commit does not match candidate")
    artifacts = identity.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise SupplyChainEvidenceError("artifact identity has no artifacts")
    subjects: dict[str, str] = {}
    for item in artifacts:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise SupplyChainEvidenceError("artifact identity contains an invalid subject")
        name, digest = item["name"].strip(), item.get("sha256")
        if not name or name in subjects or not isinstance(digest, str) or len(digest) != 64:
            raise SupplyChainEvidenceError("artifact identity contains an invalid digest")
        subjects[name] = digest
    if not sboms:
        raise SupplyChainEvidenceError("at least one SBOM is required")
    sbom_digests: dict[str, str] = {}
    for path in sboms:
        document = _load(path)
        if not (
            isinstance(document.get("spdxVersion"), str)
            and isinstance(document.get("packages"), list)
            or isinstance(document.get("bomFormat"), str)
            and isinstance(document.get("components"), list)
        ):
            raise SupplyChainEvidenceError(f"SBOM is neither SPDX nor CycloneDX: {path}")
        sbom_digests[str(path)] = _sha256(path)
    if provenance is None:
        raise SupplyChainEvidenceError("provenance evidence is required")
    statement = _load(provenance)
    if statement.get("commit") != commit:
        raise SupplyChainEvidenceError("provenance commit does not match candidate")
    if not statement.get("subject") and not statement.get("subjects"):
        raise SupplyChainEvidenceError("provenance has no subjects")
    provenance_digest = _sha256(provenance)
    return {
        "schema": "ronin.supply-chain-evidence/v1",
        "commit": commit,
        "artifact_digests": subjects,
        "sbom_digests": sbom_digests,
        "provenance_sha256": provenance_digest,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--artifact-identity", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, action="append", required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate(
            commit=args.commit,
            artifact_identity=args.artifact_identity,
            sboms=args.sbom,
            provenance=args.provenance,
        )
    except SupplyChainEvidenceError as exc:
        print(f"supply-chain evidence invalid: {exc}")
        return 2
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
