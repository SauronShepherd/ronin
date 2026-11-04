from __future__ import annotations

import hashlib
import io
import json
import runpy
import tarfile
from pathlib import Path

import pytest

from tools.bind_container_sbom import (
    ContainerSbomError,
    bind_container_sbom,
    verify_bound_container_sbom,
)
from tools.bind_container_sbom import (
    main as bind_main,
)
from tools.supply_chain_evidence import SupplyChainEvidenceError, validate
from tools.supply_chain_evidence import main as supply_chain_main

_COMMIT = "a" * 40


def _tar_member(archive: tarfile.TarFile, name: str, value: bytes) -> None:
    member = tarfile.TarInfo(name)
    member.size = len(value)
    archive.addfile(member, io.BytesIO(value))


def _write_image_archive(path: Path, reference: str) -> str:
    config = json.dumps({"architecture": "amd64", "os": "linux"}).encode()
    config_digest = hashlib.sha256(config).hexdigest()
    manifest = json.dumps(
        [{"Config": f"blobs/sha256/{config_digest}", "RepoTags": [reference], "Layers": []}]
    ).encode()
    with tarfile.open(path, mode="w") as archive:
        _tar_member(archive, "manifest.json", manifest)
        _tar_member(archive, f"blobs/sha256/{config_digest}", config)
    return config_digest


def _write_trivy_sbom(path: Path, image_name: str, reference: str, config_digest: str) -> None:
    value = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "serialNumber": "urn:uuid:11111111-1111-4111-8111-111111111111",
        "version": 1,
        "metadata": {
            "tools": {
                "components": [{"type": "application", "name": "trivy", "version": "0.76.1"}]
            },
            "component": {
                "type": "container",
                "name": f"/scan/{image_name}",
                "properties": [
                    {"name": "aquasecurity:trivy:ImageID", "value": f"sha256:{config_digest}"},
                    {"name": "aquasecurity:trivy:Reference", "value": reference},
                ],
            },
        },
        "components": [
            {
                "type": "operating-system",
                "name": "alpine",
                "version": "3.24.3",
                "bom-ref": "os:alpine@3.24.3",
                "properties": [{"name": "aquasecurity:trivy:Class", "value": "os-pkgs"}],
            },
            {
                "type": "library",
                "name": "musl",
                "version": "1.2.5-r0",
                "bom-ref": "pkg:apk/alpine/musl@1.2.5-r0",
                "purl": "pkg:apk/alpine/musl@1.2.5-r0",
                "properties": [{"name": "aquasecurity:trivy:Class", "value": "os-pkgs"}],
            },
        ],
    }
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _candidate(tmp_path: Path, labels: tuple[str, ...] = ("runtime", "probe")):
    image_pairs: list[tuple[Path, Path]] = []
    artifacts = []
    for label in labels:
        archive = tmp_path / f"ronin-{label}.tar"
        reference = f"ronin:{label}-candidate"
        config_digest = _write_image_archive(archive, reference)
        raw_sbom = tmp_path / f"ronin-{label}-trivy.cdx.json"
        _write_trivy_sbom(raw_sbom, archive.name, reference, config_digest)
        image_pairs.append((archive, raw_sbom))
        for path in (archive, raw_sbom):
            artifacts.append(
                {
                    "name": path.name,
                    "kind": "evidence",
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "size": path.stat().st_size,
                }
            )
    identity_value = {
        "schema": "ronin.artifact-identity/v1",
        "commit": _COMMIT,
        "artifacts": artifacts,
    }
    identity = tmp_path / "artifact-identity.json"
    identity.write_text(json.dumps(identity_value, sort_keys=True), encoding="utf-8")
    return identity, identity_value, image_pairs


def _refresh_identity_digest(identity: Path, artifact: Path) -> None:
    value = json.loads(identity.read_text(encoding="utf-8"))
    for item in value["artifacts"]:
        if item["name"] == artifact.name:
            body = artifact.read_bytes()
            item["sha256"] = hashlib.sha256(body).hexdigest()
            item["size"] = len(body)
            break
    else:
        raise AssertionError(f"artifact is missing from identity: {artifact.name}")
    identity.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _application_sbom(tmp_path: Path, identity_value: dict) -> Path:
    path = tmp_path / "ronin-application.cdx.json"
    path.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.6",
                "metadata": {"component": {"type": "application", "name": "ronin"}},
                "components": [
                    {
                        "type": "file",
                        "name": artifact["name"],
                        "hashes": [{"alg": "SHA-256", "content": artifact["sha256"]}],
                    }
                    for artifact in identity_value["artifacts"]
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _provenance(tmp_path: Path, identity_value: dict) -> Path:
    path = tmp_path / "provenance.json"
    path.write_text(
        json.dumps(
            {
                "commit": _COMMIT,
                "subject": [
                    {"name": item["name"], "digest": {"sha256": item["sha256"]}}
                    for item in identity_value["artifacts"]
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _bound_sboms(identity: Path, image_pairs: list[tuple[Path, Path]], tmp_path: Path):
    paths = []
    for archive, raw_sbom in image_pairs:
        bound = bind_container_sbom(raw_sbom, archive, identity)
        path = tmp_path / f"{archive.stem}-bound.cdx.json"
        path.write_text(json.dumps(bound, sort_keys=True), encoding="utf-8")
        paths.append(path)
    return paths


def test_binder_records_exact_archive_identity_and_verifies_unchanged_inventory(tmp_path):
    identity, _, image_pairs = _candidate(tmp_path)
    archive, raw_sbom = image_pairs[0]

    bound = bind_container_sbom(raw_sbom, archive, identity, expected_commit=_COMMIT)
    summary = verify_bound_container_sbom(
        bound,
        artifact_identity=identity,
        artifact_directory=tmp_path,
    )
    properties = {
        item["name"]: item["value"] for item in bound["metadata"]["component"]["properties"]
    }

    assert summary == {
        "archive_name": archive.name,
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "config_sha256": properties["ronin:container-config-sha256"],
        "reference": "ronin:runtime-candidate",
        "trivy_version": "0.76.1",
        "os_package_count": 1,
    }


@pytest.mark.parametrize("mutation", ["image-id", "reference", "missing-packages"])
def test_binder_rejects_inconsistent_or_incomplete_trivy_inventory(tmp_path, mutation):
    archive = tmp_path / "ronin-runtime.tar"
    reference = "ronin:runtime-candidate"
    config_digest = _write_image_archive(archive, reference)
    raw_sbom = tmp_path / "ronin-runtime-trivy.cdx.json"
    _write_trivy_sbom(raw_sbom, archive.name, reference, config_digest)
    document = json.loads(raw_sbom.read_text(encoding="utf-8"))
    if mutation == "image-id":
        document["metadata"]["component"]["properties"][0]["value"] = "sha256:" + "0" * 64
    elif mutation == "reference":
        document["metadata"]["component"]["properties"][1]["value"] = "ronin:other"
    else:
        document["components"] = [
            item for item in document["components"] if item["type"] != "library"
        ]
    raw_sbom.write_text(json.dumps(document), encoding="utf-8")
    artifacts = [
        {
            "name": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in (archive, raw_sbom)
    ]
    identity = tmp_path / "identity.json"
    identity.write_text(
        json.dumps(
            {"schema": "ronin.artifact-identity/v1", "commit": _COMMIT, "artifacts": artifacts}
        ),
        encoding="utf-8",
    )

    message = {
        "image-id": "config digest",
        "reference": "reference",
        "missing-packages": "package inventory",
    }[mutation]
    with pytest.raises(ContainerSbomError, match=message):
        bind_container_sbom(raw_sbom, archive, identity)


def test_binder_rejects_archives_or_scan_sboms_changed_after_identity(tmp_path):
    identity, _, image_pairs = _candidate(tmp_path, labels=("runtime",))
    archive, raw_sbom = image_pairs[0]
    archive.write_bytes(archive.read_bytes() + b"changed")
    with pytest.raises(ContainerSbomError, match="image archive is not bound"):
        bind_container_sbom(raw_sbom, archive, identity)


def test_binder_cli_writes_candidate_bound_cyclonedx(tmp_path, monkeypatch):
    identity, _, image_pairs = _candidate(tmp_path, labels=("runtime",))
    archive, raw_sbom = image_pairs[0]
    output = tmp_path / "runtime-bound.cdx.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "bind_container_sbom",
            "--trivy-sbom",
            str(raw_sbom),
            "--image-archive",
            str(archive),
            "--artifact-identity",
            str(identity),
            "--expected-commit",
            _COMMIT,
            "--output",
            str(output),
        ],
    )

    assert bind_main() == 0
    assert (
        json.loads(output.read_text(encoding="utf-8"))["metadata"]["component"]["type"]
        == "container"
    )


def test_supply_chain_requires_and_reports_two_reverified_container_inventories(tmp_path):
    identity, identity_value, image_pairs = _candidate(tmp_path)
    app_sbom = _application_sbom(tmp_path, identity_value)
    provenance = _provenance(tmp_path, identity_value)
    bound_paths = _bound_sboms(identity, image_pairs, tmp_path)

    result = validate(
        commit=_COMMIT,
        artifact_identity=identity,
        sboms=[app_sbom, *bound_paths],
        provenance=provenance,
        artifact_directory=tmp_path,
        require_container_inventory=True,
    )

    assert [item["archive_name"] for item in result["container_image_inventory"]] == [
        "ronin-probe.tar",
        "ronin-runtime.tar",
    ]
    assert all(item["os_package_count"] == 1 for item in result["container_image_inventory"])


def test_supply_chain_cli_requires_and_writes_two_container_inventories(tmp_path, monkeypatch):
    identity, identity_value, image_pairs = _candidate(tmp_path)
    app_sbom = _application_sbom(tmp_path, identity_value)
    provenance = _provenance(tmp_path, identity_value)
    bound_paths = _bound_sboms(identity, image_pairs, tmp_path)
    output = tmp_path / "supply-chain.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "supply_chain_evidence",
            "--commit",
            _COMMIT,
            "--artifact-identity",
            str(identity),
            "--artifact-directory",
            str(tmp_path),
            "--sbom",
            str(app_sbom),
            "--sbom",
            str(bound_paths[0]),
            "--sbom",
            str(bound_paths[1]),
            "--require-container-inventory",
            "--provenance",
            str(provenance),
            "--output",
            str(output),
        ],
    )

    assert supply_chain_main() == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert len(result["container_image_inventory"]) == 2


def test_supply_chain_rejects_tampered_bound_sbom_and_missing_second_image(tmp_path):
    identity, identity_value, image_pairs = _candidate(tmp_path)
    app_sbom = _application_sbom(tmp_path, identity_value)
    provenance = _provenance(tmp_path, identity_value)
    bound_paths = _bound_sboms(identity, image_pairs, tmp_path)
    altered = json.loads(bound_paths[0].read_text(encoding="utf-8"))
    altered["components"][1]["version"] = "tampered"
    bound_paths[0].write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(SupplyChainEvidenceError, match="differs from the identity-pinned"):
        validate(
            commit=_COMMIT,
            artifact_identity=identity,
            sboms=[app_sbom, *bound_paths],
            provenance=provenance,
            artifact_directory=tmp_path,
            require_container_inventory=True,
        )

    bound_paths = _bound_sboms(identity, image_pairs[:1], tmp_path)
    with pytest.raises(SupplyChainEvidenceError, match="at least two distinct"):
        validate(
            commit=_COMMIT,
            artifact_identity=identity,
            sboms=[app_sbom, *bound_paths],
            provenance=provenance,
            artifact_directory=tmp_path,
            require_container_inventory=True,
        )


def test_supply_chain_rejects_container_bom_without_artifact_directory(tmp_path):
    identity, identity_value, image_pairs = _candidate(tmp_path, labels=("runtime",))
    app_sbom = _application_sbom(tmp_path, identity_value)
    provenance = _provenance(tmp_path, identity_value)
    bound = _bound_sboms(identity, image_pairs, tmp_path)

    with pytest.raises(SupplyChainEvidenceError, match="requires the directory"):
        validate(
            commit=_COMMIT,
            artifact_identity=identity,
            sboms=[app_sbom, *bound],
            provenance=provenance,
        )


def test_binder_rejects_bad_identity_expected_commit_and_unbound_scan(tmp_path):
    identity, _, image_pairs = _candidate(tmp_path, labels=("runtime",))
    archive, raw_sbom = image_pairs[0]
    with pytest.raises(ContainerSbomError, match="expected candidate"):
        bind_container_sbom(raw_sbom, archive, identity, expected_commit="b" * 40)

    original_identity = identity.read_text(encoding="utf-8")
    identity.write_text("{}", encoding="utf-8")
    with pytest.raises(ContainerSbomError, match="schema"):
        bind_container_sbom(raw_sbom, archive, identity)
    identity.write_text(original_identity, encoding="utf-8")

    raw_sbom.write_text(raw_sbom.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ContainerSbomError, match="raw Trivy SBOM is not bound"):
        bind_container_sbom(raw_sbom, archive, identity)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("spec-version", "CycloneDX 1.7"),
        ("root-type", "container root component"),
        ("root-name", "does not identify the supplied"),
        ("missing-image-id", "exactly one aquasecurity:trivy:ImageID"),
        ("scanner-version", "exactly one scanner version"),
        ("components-not-array", "package inventory"),
        ("missing-os", "operating system component"),
        ("prebound", "already contains Ronin"),
        ("invalid-package", "invalid component"),
    ],
)
def test_binder_rejects_incomplete_candidate_sbom(tmp_path, mutation, message):
    identity, _, image_pairs = _candidate(tmp_path, labels=("runtime",))
    archive, raw_sbom = image_pairs[0]
    document = json.loads(raw_sbom.read_text(encoding="utf-8"))
    root = document["metadata"]["component"]
    if mutation == "spec-version":
        document["specVersion"] = "1.6"
    elif mutation == "root-type":
        root["type"] = "application"
    elif mutation == "root-name":
        root["name"] = "/scan/other.tar"
    elif mutation == "missing-image-id":
        root["properties"] = [
            item for item in root["properties"] if item["name"] != "aquasecurity:trivy:ImageID"
        ]
    elif mutation == "scanner-version":
        document["metadata"]["tools"]["components"] = []
    elif mutation == "components-not-array":
        document["components"] = None
    elif mutation == "missing-os":
        document["components"] = [
            item for item in document["components"] if item["type"] != "operating-system"
        ]
    elif mutation == "prebound":
        root["properties"].append({"name": "ronin:source-commit", "value": _COMMIT})
    else:
        package = next(item for item in document["components"] if item["type"] == "library")
        package["bom-ref"] = None
    raw_sbom.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
    _refresh_identity_digest(identity, raw_sbom)

    with pytest.raises(ContainerSbomError, match=message):
        bind_container_sbom(raw_sbom, archive, identity)


def test_bound_sbom_verifier_rejects_invalid_root_unsafe_name_and_missing_subject(tmp_path):
    identity, _, image_pairs = _candidate(tmp_path, labels=("runtime",))
    archive, raw_sbom = image_pairs[0]
    bound = bind_container_sbom(raw_sbom, archive, identity)
    with pytest.raises(ContainerSbomError, match="container root component"):
        verify_bound_container_sbom(
            {"metadata": {"component": {"type": "application"}}},
            artifact_identity=identity,
            artifact_directory=tmp_path,
        )

    unsafe = json.loads(json.dumps(bound))
    for item in unsafe["metadata"]["component"]["properties"]:
        if item["name"] == "ronin:container-archive-name":
            item["value"] = "../runtime.tar"
    with pytest.raises(ContainerSbomError, match="plain file names"):
        verify_bound_container_sbom(
            unsafe,
            artifact_identity=identity,
            artifact_directory=tmp_path,
        )

    missing = json.loads(json.dumps(bound))
    for item in missing["metadata"]["component"]["properties"]:
        if item["name"] == "ronin:container-archive-name":
            item["value"] = "missing.tar"
        elif item["name"] == "ronin:container-scan-sbom-name":
            item["value"] = "missing-trivy.cdx.json"
    with pytest.raises(ContainerSbomError, match="archive or raw Trivy SBOM is missing"):
        verify_bound_container_sbom(
            missing,
            artifact_identity=identity,
            artifact_directory=tmp_path,
        )


def test_binder_cli_reports_invalid_input_without_traceback(tmp_path, monkeypatch):
    identity, _, image_pairs = _candidate(tmp_path, labels=("runtime",))
    archive, _ = image_pairs[0]
    monkeypatch.setattr(
        "sys.argv",
        [
            "bind_container_sbom",
            "--trivy-sbom",
            str(tmp_path / "missing.cdx.json"),
            "--image-archive",
            str(archive),
            "--artifact-identity",
            str(identity),
            "--output",
            str(tmp_path / "output.cdx.json"),
        ],
    )
    with pytest.raises(SystemExit, match="2"):
        bind_main()


def test_binder_module_entrypoint_shows_help(monkeypatch):
    module_path = Path(__file__).resolve().parents[1] / "tools" / "bind_container_sbom.py"
    monkeypatch.setattr("sys.argv", ["bind_container_sbom", "--help"])

    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(module_path), run_name="__main__")
    assert error.value.code == 0
