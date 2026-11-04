"""Bind a Trivy container SBOM to the exact image archive and candidate."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any

from tools.generate_release_sbom import _load_identity

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_ARCHIVE_METADATA_BYTES = 1024 * 1024


class ContainerSbomError(ValueError):
    """Raised when a container SBOM cannot be bound to the candidate image."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContainerSbomError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ContainerSbomError(f"{label} must be a JSON object")
    return value


def _property_values(component: dict[str, Any], name: str) -> list[str]:
    properties = component.get("properties", [])
    if not isinstance(properties, list):
        raise ContainerSbomError("Trivy container component properties must be an array")
    values: list[str] = []
    for item in properties:
        if not isinstance(item, dict):
            raise ContainerSbomError("Trivy container SBOM contains an invalid property")
        property_name, value = item.get("name"), item.get("value")
        if not isinstance(property_name, str) or not isinstance(value, str):
            raise ContainerSbomError("Trivy container SBOM contains an invalid property")
        if property_name == name:
            values.append(value)
    return values


def _one_property(component: dict[str, Any], name: str) -> str:
    values = _property_values(component, name)
    if len(values) != 1 or not values[0].strip():
        raise ContainerSbomError(f"Trivy container SBOM must contain exactly one {name} property")
    return values[0]


def _os_package_count(components: list[Any]) -> int:
    """Validate and count package URLs from OS package ecosystems in Trivy output."""
    refs: set[str] = set()
    count = 0
    for item in components:
        if not isinstance(item, dict) or item.get("type") != "library":
            continue
        purl = item.get("purl")
        if not isinstance(purl, str) or not purl.startswith(("pkg:apk/", "pkg:deb/", "pkg:rpm/")):
            continue
        name, version, bom_ref = item.get("name"), item.get("version"), item.get("bom-ref")
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(version, str)
            or not version.strip()
            or not isinstance(bom_ref, str)
            or not bom_ref.strip()
            or bom_ref in refs
        ):
            raise ContainerSbomError("Trivy OS package inventory contains an invalid component")
        refs.add(bom_ref)
        count += 1
    return count


def _archive_identity(image_archive: Path) -> tuple[str, set[str]]:
    """Return the Docker config digest and repository tags from a single-image TAR."""
    try:
        with tarfile.open(image_archive, mode="r:*") as archive:
            manifests = [
                member for member in archive.getmembers() if member.name == "manifest.json"
            ]
            if len(manifests) != 1 or not manifests[0].isfile():
                raise ContainerSbomError("image archive must contain exactly one manifest.json")
            if manifests[0].size > _MAX_ARCHIVE_METADATA_BYTES:
                raise ContainerSbomError("image archive manifest.json is unexpectedly large")
            manifest_stream = archive.extractfile(manifests[0])
            if manifest_stream is None:
                raise ContainerSbomError("image archive manifest.json is unreadable")
            manifest = json.loads(manifest_stream.read().decode("utf-8"))
            if (
                not isinstance(manifest, list)
                or len(manifest) != 1
                or not isinstance(manifest[0], dict)
            ):
                raise ContainerSbomError("image archive must contain exactly one image entry")
            entry = manifest[0]
            config_path = entry.get("Config")
            tags = entry.get("RepoTags")
            if (
                not isinstance(config_path, str)
                or not isinstance(tags, list)
                or not tags
                or any(not isinstance(tag, str) or not tag.strip() for tag in tags)
                or len(tags) != len(set(tags))
            ):
                raise ContainerSbomError("image archive manifest has invalid config or tags")
            config_name = PurePosixPath(config_path)
            match = re.fullmatch(r"blobs/sha256/([0-9a-f]{64})", config_path)
            if config_name.is_absolute() or ".." in config_name.parts or match is None:
                raise ContainerSbomError("image archive config path must be a SHA-256 blob")
            config_members = [
                member for member in archive.getmembers() if member.name == config_path
            ]
            if len(config_members) != 1:
                raise ContainerSbomError("image archive must contain exactly one config blob")
            config_member = config_members[0]
            if not config_member.isfile():
                raise ContainerSbomError("image archive config blob must be a regular file")
            if config_member.size > _MAX_ARCHIVE_METADATA_BYTES:
                raise ContainerSbomError("image archive config blob is unexpectedly large")
            config_stream = archive.extractfile(config_member)
            if config_stream is None:
                raise ContainerSbomError("image archive config blob is unreadable")
            config_digest = hashlib.sha256(config_stream.read()).hexdigest()
            if config_digest != match.group(1):
                raise ContainerSbomError("image archive config digest does not match its path")
    except (OSError, tarfile.TarError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContainerSbomError(f"cannot inspect Docker image archive: {image_archive}") from exc
    return config_digest, set(tags)


def bind_container_sbom(
    trivy_sbom_path: Path,
    image_archive: Path,
    artifact_identity: Path,
    *,
    expected_commit: str | None = None,
) -> dict[str, Any]:
    """Add candidate and exact-image-archive bindings to a Trivy CycloneDX SBOM.

    The candidate identity must already include both the image TAR and the raw
    Trivy SBOM. This makes the scanner input, scanner output, and source commit
    part of the same release evidence set.
    """
    try:
        identity = _load_identity(artifact_identity)
    except ValueError as exc:
        raise ContainerSbomError(str(exc)) from exc
    commit = identity["commit"]
    if expected_commit is not None and commit != expected_commit:
        raise ContainerSbomError("artifact identity commit does not match expected candidate")

    artifacts = {item["name"]: item["sha256"] for item in identity["artifacts"]}
    archive_digest = _sha256_file(image_archive)
    if artifacts.get(image_archive.name) != archive_digest:
        raise ContainerSbomError("image archive is not bound to artifact identity")
    scan_digest = _sha256_file(trivy_sbom_path)
    if artifacts.get(trivy_sbom_path.name) != scan_digest:
        raise ContainerSbomError("raw Trivy SBOM is not bound to artifact identity")

    document = _load_json(trivy_sbom_path, "Trivy CycloneDX SBOM")
    if document.get("bomFormat") != "CycloneDX" or document.get("specVersion") != "1.7":
        raise ContainerSbomError("Trivy SBOM must be CycloneDX 1.7")
    metadata = document.get("metadata")
    root = metadata.get("component") if isinstance(metadata, dict) else None
    if not isinstance(root, dict) or root.get("type") != "container":
        raise ContainerSbomError("Trivy SBOM must identify a container root component")
    reported_name = root.get("name")
    if (
        not isinstance(reported_name, str)
        or reported_name.replace("\\", "/").rsplit("/", 1)[-1] != image_archive.name
    ):
        raise ContainerSbomError("Trivy SBOM root does not identify the supplied image archive")

    config_digest, repository_tags = _archive_identity(image_archive)
    image_id = _one_property(root, "aquasecurity:trivy:ImageID")
    reference = _one_property(root, "aquasecurity:trivy:Reference")
    if image_id != f"sha256:{config_digest}":
        raise ContainerSbomError("Trivy image config digest does not match the supplied archive")
    if reference not in repository_tags:
        raise ContainerSbomError("Trivy image reference does not match the supplied archive tags")

    tools = metadata.get("tools") if isinstance(metadata, dict) else None
    tool_components = tools.get("components") if isinstance(tools, dict) else None
    trivy_versions = (
        [
            item.get("version")
            for item in tool_components
            if isinstance(item, dict) and item.get("name") == "trivy"
        ]
        if isinstance(tool_components, list)
        else []
    )
    if (
        len(trivy_versions) != 1
        or not isinstance(trivy_versions[0], str)
        or not trivy_versions[0].strip()
    ):
        raise ContainerSbomError("Trivy SBOM must identify exactly one scanner version")

    components = document.get("components")
    if not isinstance(components, list) or not components:
        raise ContainerSbomError("Trivy SBOM must contain a package inventory")
    if not any(
        isinstance(item, dict) and item.get("type") == "operating-system" for item in components
    ):
        raise ContainerSbomError("Trivy SBOM is missing its operating system component")
    package_count = _os_package_count(components)
    if package_count == 0:
        raise ContainerSbomError("Trivy SBOM is missing its operating-system package inventory")

    bound = copy.deepcopy(document)
    bound_root = bound["metadata"]["component"]
    if any(
        isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and item["name"].startswith("ronin:")
        for item in bound_root.get("properties", [])
    ):
        raise ContainerSbomError("Trivy SBOM already contains Ronin binding properties")
    bound_root.setdefault("properties", []).extend(
        [
            {"name": "ronin:source-commit", "value": commit},
            {"name": "ronin:container-archive-name", "value": image_archive.name},
            {"name": "ronin:container-archive-sha256", "value": archive_digest},
            {"name": "ronin:container-config-sha256", "value": config_digest},
            {"name": "ronin:container-reference", "value": reference},
            {"name": "ronin:container-scan-sbom-name", "value": trivy_sbom_path.name},
            {"name": "ronin:container-scan-sbom-sha256", "value": scan_digest},
            {"name": "ronin:trivy-version", "value": trivy_versions[0]},
        ]
    )
    return bound


def verify_bound_container_sbom(
    bound_document: dict[str, Any],
    *,
    artifact_identity: Path,
    artifact_directory: Path,
) -> dict[str, Any]:
    """Rebuild a bound Trivy SBOM from identity-pinned source files and compare it."""
    metadata = bound_document.get("metadata")
    root = metadata.get("component") if isinstance(metadata, dict) else None
    if not isinstance(root, dict) or root.get("type") != "container":
        raise ContainerSbomError("SBOM does not contain a container root component")
    archive_name = _one_property(root, "ronin:container-archive-name")
    source_sbom_name = _one_property(root, "ronin:container-scan-sbom-name")
    if Path(archive_name).name != archive_name or Path(source_sbom_name).name != source_sbom_name:
        raise ContainerSbomError("container evidence names must be plain file names")
    image_archive = artifact_directory / archive_name
    source_sbom = artifact_directory / source_sbom_name
    if not image_archive.is_file() or not source_sbom.is_file():
        raise ContainerSbomError("identity-pinned image archive or raw Trivy SBOM is missing")
    expected = bind_container_sbom(source_sbom, image_archive, artifact_identity)
    if bound_document != expected:
        raise ContainerSbomError(
            "bound container SBOM differs from the identity-pinned Trivy inventory"
        )

    properties = {
        name: _one_property(root, name)
        for name in (
            "ronin:container-archive-sha256",
            "ronin:container-config-sha256",
            "ronin:container-reference",
            "ronin:trivy-version",
        )
    }
    components = bound_document["components"]
    package_count = _os_package_count(components)
    return {
        "archive_name": archive_name,
        "archive_sha256": properties["ronin:container-archive-sha256"],
        "config_sha256": properties["ronin:container-config-sha256"],
        "reference": properties["ronin:container-reference"],
        "trivy_version": properties["ronin:trivy-version"],
        "os_package_count": package_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="bind-container-sbom")
    parser.add_argument("--trivy-sbom", type=Path, required=True)
    parser.add_argument("--image-archive", type=Path, required=True)
    parser.add_argument("--artifact-identity", type=Path, required=True)
    parser.add_argument("--expected-commit")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = bind_container_sbom(
            args.trivy_sbom,
            args.image_archive,
            args.artifact_identity,
            expected_commit=args.expected_commit,
        )
        args.output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (OSError, ContainerSbomError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
