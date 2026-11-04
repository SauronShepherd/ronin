"""Fail-closed validation for candidate-bound release supply-chain evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from tools.bind_container_sbom import ContainerSbomError, verify_bound_container_sbom

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


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


def _normalize_hash_algorithm(value: str) -> str:
    return value.upper().replace("-", "")


def validate(
    *,
    commit: str,
    artifact_identity: Path,
    sboms: list[Path],
    provenance: Path | None = None,
    artifact_directory: Path | None = None,
    require_container_inventory: bool = False,
) -> dict[str, Any]:
    """Validate exact candidate identity, typed SBOMs, and optional provenance."""
    if not commit.strip():
        raise SupplyChainEvidenceError("commit must be non-empty")
    identity = _load(artifact_identity)
    if identity.get("schema") != "ronin.artifact-identity/v1":
        raise SupplyChainEvidenceError("unsupported artifact identity schema")
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
        if (
            not name
            or name in subjects
            or not isinstance(digest, str)
            or not _SHA256.fullmatch(digest)
        ):
            raise SupplyChainEvidenceError("artifact identity contains an invalid digest")
        subjects[name] = digest
    if not sboms:
        raise SupplyChainEvidenceError("at least one SBOM is required")
    sbom_digests: dict[str, str] = {}
    sbom_subjects: dict[str, str] = {}
    container_inventory: dict[str, dict[str, Any]] = {}
    for path in sboms:
        document = _load(path)
        packages = document.get("packages")
        components = document.get("components")
        bom_format = document.get("bomFormat")
        spec_version = document.get("specVersion")
        if document.get("spdxVersion") == "SPDX-2.3" and isinstance(packages, list):
            records = packages
            hash_field = ("checksums", "algorithm", "checksumValue")
        elif (
            bom_format == "CycloneDX"
            and spec_version in {"1.5", "1.6", "1.7"}
            and isinstance(components, list)
        ):
            records = components
            hash_field = ("hashes", "alg", "content")
        else:
            raise SupplyChainEvidenceError(f"SBOM is neither SPDX nor CycloneDX: {path}")
        metadata = document.get("metadata")
        root = metadata.get("component") if isinstance(metadata, dict) else None
        if isinstance(root, dict) and root.get("type") == "container":
            if artifact_directory is None:
                raise SupplyChainEvidenceError(
                    "container SBOM validation requires the directory containing identity artifacts"
                )
            try:
                summary = verify_bound_container_sbom(
                    document,
                    artifact_identity=artifact_identity,
                    artifact_directory=artifact_directory,
                )
            except (ContainerSbomError, OSError) as exc:
                raise SupplyChainEvidenceError(f"invalid bound container SBOM: {exc}") from exc
            archive_name = summary["archive_name"]
            if archive_name in container_inventory:
                raise SupplyChainEvidenceError(
                    f"container image has more than one SBOM: {archive_name}"
                )
            container_inventory[archive_name] = summary
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("name"), str):
                raise SupplyChainEvidenceError(f"SBOM contains an invalid component: {path}")
            name = record["name"]
            if name not in subjects:
                continue
            if document.get("bomFormat") == "CycloneDX" and record.get("type") != "file":
                raise SupplyChainEvidenceError(
                    f"SBOM artifact subject is not a file component: {name}"
                )
            hashes = record.get(hash_field[0])
            if not isinstance(hashes, list):
                raise SupplyChainEvidenceError(f"SBOM artifact subject has no hashes: {name}")
            matching_hashes = [
                item
                for item in hashes
                if isinstance(item, dict)
                and isinstance(item.get(hash_field[1]), str)
                and _normalize_hash_algorithm(item[hash_field[1]]) == "SHA256"
            ]
            if len(matching_hashes) != 1:
                raise SupplyChainEvidenceError(
                    f"SBOM artifact subject must contain exactly one SHA-256 digest: {name}"
                )
            digest = matching_hashes[0].get(hash_field[2])
            if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
                raise SupplyChainEvidenceError(
                    f"SBOM artifact subject has an invalid digest: {name}"
                )
            if name in sbom_subjects and sbom_subjects[name] != digest:
                raise SupplyChainEvidenceError(f"SBOM files disagree on artifact digest: {name}")
            sbom_subjects[name] = digest
        sbom_digests[str(path)] = _sha256(path)
    missing_subjects = sorted(
        name for name, digest in subjects.items() if sbom_subjects.get(name) != digest
    )
    if missing_subjects:
        raise SupplyChainEvidenceError(
            "SBOM artifact subjects and SHA-256 digests do not match artifact identity: "
            + ", ".join(missing_subjects)
        )
    if require_container_inventory and len(container_inventory) < 2:
        raise SupplyChainEvidenceError(
            "release requires bound Trivy inventories for at least two distinct container images"
        )
    if provenance is None:
        raise SupplyChainEvidenceError("provenance evidence is required")
    statement = _load(provenance)
    predicate = statement.get("predicate")
    if statement.get("predicateType") == "https://slsa.dev/provenance/v1":
        if statement.get("_type") != "https://in-toto.io/Statement/v1":
            raise SupplyChainEvidenceError("provenance has an unsupported in-toto statement type")
        definition = predicate.get("buildDefinition") if isinstance(predicate, dict) else None
        parameters = definition.get("externalParameters") if isinstance(definition, dict) else None
        provenance_commit = (
            parameters.get("candidateCommit") if isinstance(parameters, dict) else None
        )
        if not isinstance(parameters, dict) or parameters.get("artifactIdentitySha256") != _sha256(
            artifact_identity
        ):
            raise SupplyChainEvidenceError("provenance does not bind the artifact identity file")
        resolved = definition.get("resolvedDependencies") if isinstance(definition, dict) else None
        if not isinstance(resolved, list) or not any(
            isinstance(item, dict)
            and isinstance(item.get("digest"), dict)
            and item["digest"].get("gitCommit") == commit
            for item in resolved
        ):
            raise SupplyChainEvidenceError("provenance does not bind the source commit")
        run_details = predicate.get("runDetails") if isinstance(predicate, dict) else None
        builder = run_details.get("builder") if isinstance(run_details, dict) else None
        builder_id = builder.get("id") if isinstance(builder, dict) else None
        if not isinstance(builder_id, str) or not builder_id.strip():
            raise SupplyChainEvidenceError("provenance does not identify its builder")
    else:
        provenance_commit = statement.get("commit")
    if provenance_commit != commit:
        raise SupplyChainEvidenceError("provenance commit does not match candidate")
    statement_subjects = statement.get("subject", statement.get("subjects"))
    if not isinstance(statement_subjects, list) or not statement_subjects:
        raise SupplyChainEvidenceError("provenance has no subjects")
    proven: dict[str, str] = {}
    for item in statement_subjects:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise SupplyChainEvidenceError("provenance contains an invalid subject")
        name = item["name"].strip()
        digest = item.get("digest", {})
        sha256 = digest.get("sha256") if isinstance(digest, dict) else None
        if (
            not name
            or name in proven
            or not isinstance(sha256, str)
            or not _SHA256.fullmatch(sha256)
        ):
            raise SupplyChainEvidenceError("provenance contains an invalid subject digest")
        proven[name] = sha256
    if any(proven.get(name) != digest for name, digest in subjects.items()):
        raise SupplyChainEvidenceError("provenance subjects do not match artifact identity")
    provenance_digest = _sha256(provenance)
    return {
        "schema": "ronin.supply-chain-evidence/v1",
        "commit": commit,
        "artifact_digests": subjects,
        "sbom_digests": sbom_digests,
        "container_image_inventory": [
            container_inventory[name] for name in sorted(container_inventory)
        ],
        "provenance_sha256": provenance_digest,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--artifact-identity", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, action="append", required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument(
        "--artifact-directory",
        type=Path,
        help="directory containing the files named by artifact-identity.json",
    )
    parser.add_argument("--require-container-inventory", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate(
            commit=args.commit,
            artifact_identity=args.artifact_identity,
            sboms=args.sbom,
            provenance=args.provenance,
            artifact_directory=args.artifact_directory,
            require_container_inventory=args.require_container_inventory,
        )
    except SupplyChainEvidenceError as exc:
        print(f"supply-chain evidence invalid: {exc}")
        return 2
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
