from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tools import installed_artifact_evidence
from tools.artifact_identity import build_manifest
from tools.installed_artifact_evidence import (
    GATES,
    _artifact_digests,
    _validate_sbom,
    build_bundle,
)
from tools.release_evidence import release_verdict


def test_installed_artifact_bundle_contains_only_executed_job_gates(tmp_path: Path) -> None:
    identity = tmp_path / "artifact-identity.json"
    wheel = tmp_path / "ronin.whl"
    wheel.write_bytes(b"wheel")
    identity.write_text(json.dumps(build_manifest([wheel], commit="abc123")), encoding="utf-8")
    sbom = tmp_path / "sbom.json"
    sbom.write_text(json.dumps({"spdxVersion": "SPDX-2.3", "packages": []}), encoding="utf-8")
    bundle = build_bundle("abc123", identity, sbom)
    assert {record["gate_id"] for record in bundle["records"]} == GATES  # type: ignore[index]
    assert all("ronin.whl" in record["artifact_digests"] for record in bundle["records"])  # type: ignore[index]
    assert release_verdict(bundle, set(GATES))["status"] == "passed"


def test_installed_artifact_bundle_rejects_untyped_sbom(tmp_path: Path) -> None:
    identity = tmp_path / "artifact-identity.json"
    wheel = tmp_path / "ronin.whl"
    wheel.write_bytes(b"wheel")
    identity.write_text(json.dumps(build_manifest([wheel], commit="abc123")), encoding="utf-8")
    sbom = tmp_path / "sbom.json"
    sbom.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="SPDX or CycloneDX"):
        build_bundle("abc123", identity, sbom)


def test_artifact_identity_rejects_duplicate_or_non_hex_entries(tmp_path: Path) -> None:
    identity = tmp_path / "artifact-identity.json"
    identity.write_text(
        json.dumps(
            {
                "schema": "ronin.artifact-identity/v1",
                "commit": "abc123",
                "artifacts": [
                    {"name": "wheel", "sha256": "a" * 64},
                    {"name": "wheel", "sha256": "b" * 64},
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        _artifact_digests(identity, "abc123")
    identity.write_text(
        json.dumps(
            {
                "schema": "ronin.artifact-identity/v1",
                "commit": "abc123",
                "artifacts": [{"name": "wheel", "sha256": "g" * 64}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid SHA-256"):
        _artifact_digests(identity, "abc123")


def test_artifact_identity_binds_names_to_existing_content(tmp_path: Path) -> None:
    identity = tmp_path / "artifact-identity.json"
    wheel = tmp_path / "ronin.whl"
    wheel.write_bytes(b"wheel")
    manifest = build_manifest([wheel], commit="abc123")
    identity.write_text(json.dumps(manifest), encoding="utf-8")

    wheel.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="does not match artifact"):
        _artifact_digests(identity, "abc123")

    manifest["artifacts"] = [{"name": "missing.whl", "sha256": "a" * 64}]
    identity.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="missing artifact"):
        _artifact_digests(identity, "abc123")


def test_artifact_identity_rejects_path_traversal_names(tmp_path: Path) -> None:
    identity = tmp_path / "artifact-identity.json"
    identity.write_text(
        json.dumps(
            {
                "schema": "ronin.artifact-identity/v1",
                "commit": "abc123",
                "artifacts": [{"name": "../outside.whl", "sha256": "a" * 64}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid artifact name"):
        _artifact_digests(identity, "abc123")


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{", "cannot read artifact identity"),
        ("[]", "must be a JSON object"),
        (json.dumps({"schema": "other"}), "schema is invalid"),
        (
            json.dumps({"schema": "ronin.artifact-identity/v1", "commit": "other"}),
            "commit does not match",
        ),
        (
            json.dumps(
                {"schema": "ronin.artifact-identity/v1", "commit": "abc123", "artifacts": []}
            ),
            "must contain artifacts",
        ),
        (
            json.dumps(
                {"schema": "ronin.artifact-identity/v1", "commit": "abc123", "artifacts": [None]}
            ),
            "invalid artifact",
        ),
        (
            json.dumps(
                {
                    "schema": "ronin.artifact-identity/v1",
                    "commit": "abc123",
                    "artifacts": [{"name": " ", "sha256": "a" * 64}],
                }
            ),
            "invalid artifact name",
        ),
    ],
)
def test_artifact_identity_rejects_malformed_manifests(
    tmp_path: Path, content: str, message: str
) -> None:
    identity = tmp_path / "artifact-identity.json"
    identity.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        _artifact_digests(identity, "abc123")


def test_installed_artifact_evidence_validates_sbom_inputs_and_optional_path(
    tmp_path: Path,
) -> None:
    sbom = tmp_path / "sbom.json"
    sbom.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot read SBOM"):
        _validate_sbom(sbom)
    sbom.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a JSON object"):
        _validate_sbom(sbom)

    wheel = tmp_path / "ronin.whl"
    wheel.write_bytes(b"wheel")
    identity = tmp_path / "artifact-identity.json"
    identity.write_text(json.dumps(build_manifest([wheel], commit="abc123")), encoding="utf-8")
    bundle = build_bundle("abc123", identity)
    assert all(str(identity) in record["artifact_digests"] for record in bundle["records"])
    sbom.write_text(json.dumps({"bomFormat": "CycloneDX", "components": []}), encoding="utf-8")
    _validate_sbom(sbom)


def test_installed_artifact_evidence_cli_writes_bundle_and_verdict(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    wheel = tmp_path / "ronin.whl"
    wheel.write_bytes(b"wheel")
    identity = tmp_path / "artifact-identity.json"
    identity.write_text(json.dumps(build_manifest([wheel], commit="abc123")), encoding="utf-8")
    sbom = tmp_path / "sbom.json"
    sbom.write_text(json.dumps({"spdxVersion": "SPDX-2.3", "packages": []}), encoding="utf-8")
    output = tmp_path / "bundle.json"
    verdict_output = tmp_path / "verdict.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "installed-artifact-evidence",
            "--commit",
            "abc123",
            "--artifact-identity",
            str(identity),
            "--sbom",
            str(sbom),
            "--output",
            str(output),
            "--verdict-output",
            str(verdict_output),
        ],
    )
    assert installed_artifact_evidence.main() == 0
    assert json.loads(output.read_text(encoding="utf-8"))["commit"] == "abc123"
    assert json.loads(verdict_output.read_text(encoding="utf-8"))["status"] == "passed"
    assert '"status": "passed"' in capsys.readouterr().out
