"""Generate and verify candidate-bound CycloneDX release SBOMs."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path
from typing import Any
from uuid import uuid4

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LOCKED_REQUIREMENT = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9.+!_-]*)$")


def _load_identity(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read artifact identity: {path}") from exc
    if not isinstance(value, dict) or value.get("schema") != "ronin.artifact-identity/v1":
        raise ValueError("unsupported artifact identity schema")
    commit = value.get("commit")
    artifacts = value.get("artifacts")
    if not isinstance(commit, str) or not commit or commit != commit.strip():
        raise ValueError("artifact identity commit must be non-empty trimmed text")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("artifact identity must contain artifacts")
    names: set[str] = set()
    for item in artifacts:
        if not isinstance(item, dict):
            raise ValueError("artifact identity contains an invalid artifact")
        name, digest = item.get("name"), item.get("sha256")
        if (
            not isinstance(name, str)
            or not name
            or name != name.strip()
            or Path(name).name != name
            or name in names
            or not isinstance(digest, str)
            or not _SHA256.fullmatch(digest)
        ):
            raise ValueError("artifact identity contains an invalid name or digest")
        names.add(name)
    return value


def _lock_components(lock_path: Path) -> list[dict[str, Any]]:
    try:
        lines = lock_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"cannot read dependency lock: {lock_path}") from exc
    packages: dict[str, dict[str, set[str]]] = {}
    for line in lines:
        candidate = line.strip().removesuffix("\\").strip()
        if not candidate or candidate.startswith(("#", "--")):
            continue
        requirement, _, marker = candidate.partition(";")
        requirement = requirement.strip().split(" ", 1)[0]
        marker = re.sub(r"\\s+", " ", marker.strip())
        match = _LOCKED_REQUIREMENT.fullmatch(requirement)
        if match is None:
            continue
        raw_name, version = match.groups()
        name = re.sub(r"[-_.]+", "-", raw_name).lower()
        versions = packages.setdefault(name, {})
        previous_versions = set(versions)
        if previous_versions - {version}:
            previous_markers = {
                previous_marker
                for previous_version in previous_versions
                for previous_marker in versions[previous_version]
            }
            if not marker or not previous_markers or "" in previous_markers:
                raise ValueError(f"dependency lock contains conflicting versions for {name}")
        versions.setdefault(version, set()).add(marker)
    if not packages:
        raise ValueError(f"dependency lock contains no exact name==version entries: {lock_path}")
    components = []
    for name, versions in sorted(packages.items()):
        for version, markers in sorted(versions.items()):
            properties = [{"name": "ronin:inventory-source", "value": lock_path.name}]
            properties.extend(
                {"name": "ronin:environment-marker", "value": marker}
                for marker in sorted(markers)
                if marker
            )
            components.append(
                {
                    "type": "library",
                    "name": name,
                    "version": version,
                    "bom-ref": f"pkg:pypi/{name}@{version}",
                    "purl": f"pkg:pypi/{name}@{version}",
                    "properties": properties,
                }
            )
    return components


def build_sbom(
    artifact_identity: Path,
    requirements_lock: Path,
    *,
    project_file: Path = Path("pyproject.toml"),
) -> dict[str, Any]:
    """Build a CycloneDX BOM for identified release files and a pinned Python lock."""
    identity = _load_identity(artifact_identity)
    try:
        project = tomllib.loads(project_file.read_text(encoding="utf-8"))["project"]
        project_name, project_version = project["name"], project["version"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"cannot read project name and version from {project_file}") from exc
    if (
        not isinstance(project_name, str)
        or not project_name
        or project_name != project_name.strip()
        or not isinstance(project_version, str)
        or not project_version
        or project_version != project_version.strip()
    ):
        raise ValueError("project name and version must be strings")

    artifact_components = []
    for artifact in sorted(identity["artifacts"], key=lambda item: item["name"]):
        digest = artifact["sha256"]
        component: dict[str, Any] = {
            "type": "file",
            "name": artifact["name"],
            "bom-ref": f"urn:ronin:artifact:sha256:{digest}",
            "hashes": [{"alg": "SHA-256", "content": digest}],
        }
        kind = artifact.get("kind")
        if isinstance(kind, str) and kind:
            component["properties"] = [{"name": "ronin:artifact-kind", "value": kind}]
        artifact_components.append(component)

    root_ref = f"pkg:pypi/{re.sub(r'[-_.]+', '-', project_name).lower()}@{project_version}"
    root = {
        "type": "application",
        "name": project_name,
        "version": project_version,
        "bom-ref": root_ref,
        "properties": [
            {"name": "ronin:source-commit", "value": identity["commit"]},
            {"name": "ronin:dependency-inventory", "value": requirements_lock.name},
        ],
    }
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid4()}",
        "version": 1,
        "metadata": {"component": root},
        "components": artifact_components + _lock_components(requirements_lock),
    }


def verify_sbom(
    sbom_path: Path,
    artifact_identity: Path,
    requirements_lock: Path,
    *,
    expected_commit: str | None = None,
) -> None:
    try:
        bom = json.loads(sbom_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read CycloneDX SBOM: {sbom_path}") from exc
    identity = _load_identity(artifact_identity)
    if expected_commit is not None and identity["commit"] != expected_commit:
        raise ValueError("artifact identity commit does not match expected candidate")
    if (
        not isinstance(bom, dict)
        or bom.get("bomFormat") != "CycloneDX"
        or bom.get("specVersion") != "1.6"
    ):
        raise ValueError("SBOM must be a CycloneDX 1.6 document")
    serial = bom.get("serialNumber")
    if not isinstance(serial, str) or not re.fullmatch(
        r"urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", serial
    ):
        raise ValueError("CycloneDX SBOM serialNumber must be an RFC 4122 UUID URN")
    metadata = bom.get("metadata")
    root = metadata.get("component") if isinstance(metadata, dict) else None
    if not isinstance(root, dict):
        raise ValueError("CycloneDX SBOM metadata must identify the root application component")
    root_properties = root.get("properties", [])
    if not isinstance(root_properties, list):
        raise ValueError("SBOM source commit does not match artifact identity")
    source_commit_values = [
        item.get("value")
        for item in root_properties
        if isinstance(item, dict) and item.get("name") == "ronin:source-commit"
    ]
    if any(not isinstance(value, str) for value in source_commit_values):
        raise ValueError("SBOM source commit does not match artifact identity")
    source_commits = set(source_commit_values)
    if source_commits != {identity["commit"]}:
        raise ValueError("SBOM source commit does not match artifact identity")
    components = bom.get("components")
    if not isinstance(components, list):
        raise ValueError("CycloneDX SBOM components must be an array")
    actual_artifacts: dict[str, str] = {}
    for item in components:
        if not isinstance(item, dict):
            raise ValueError("CycloneDX SBOM contains an invalid component")
        component_type = item.get("type")
        if not isinstance(component_type, str) or component_type not in {"file", "library"}:
            raise ValueError("CycloneDX SBOM contains an unsupported component type")
        name = item.get("name")
        hashes = item.get("hashes", [])
        if not isinstance(name, str) or not isinstance(hashes, list):
            raise ValueError("CycloneDX SBOM component has an invalid name or hashes")
        for entry in hashes:
            if not isinstance(entry, dict):
                raise ValueError("CycloneDX SBOM contains an invalid hash")
            algorithm = entry.get("alg")
            if not isinstance(algorithm, str):
                raise ValueError("CycloneDX SBOM contains an invalid hash algorithm")
            if algorithm.upper().replace("-", "") != "SHA256":
                continue
            digest = entry.get("content")
            if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
                raise ValueError("CycloneDX SBOM contains an invalid SHA-256 digest")
            if component_type == "file":
                if name in actual_artifacts:
                    if actual_artifacts[name] != digest:
                        raise ValueError(f"CycloneDX SBOM has conflicting digests for {name}")
                    raise ValueError(f"CycloneDX SBOM contains duplicate file component {name}")
                actual_artifacts[name] = digest
    expected = {item["name"]: item["sha256"] for item in identity["artifacts"]}
    if actual_artifacts != expected:
        raise ValueError("CycloneDX SBOM artifact subjects do not match artifact identity")
    expected_packages = {
        (component["name"], component["version"])
        for component in _lock_components(requirements_lock)
    }
    actual_packages = [
        (item.get("name"), item.get("version"))
        for item in components
        if isinstance(item, dict) and item.get("type") == "library"
    ]
    if any(
        not isinstance(name, str) or not isinstance(version, str)
        for name, version in actual_packages
    ):
        raise ValueError("CycloneDX SBOM dependency inventory does not match the lock file")
    if (
        len(actual_packages) != len(set(actual_packages))
        or set(actual_packages) != expected_packages
    ):
        raise ValueError("CycloneDX SBOM dependency inventory does not match the lock file")


def main() -> int:
    parser = argparse.ArgumentParser(prog="generate-release-sbom")
    parser.add_argument("--artifact-identity", type=Path, required=True)
    parser.add_argument("--requirements-lock", type=Path, required=True)
    parser.add_argument("--project-file", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--expected-commit")
    args = parser.parse_args()
    try:
        if args.verify:
            verify_sbom(
                args.output,
                args.artifact_identity,
                args.requirements_lock,
                expected_commit=args.expected_commit,
            )
        else:
            args.output.write_text(
                json.dumps(
                    build_sbom(
                        args.artifact_identity,
                        args.requirements_lock,
                        project_file=args.project_file,
                    ),
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
