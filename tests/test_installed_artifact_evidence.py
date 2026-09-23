from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.artifact_identity import build_manifest
from tools.installed_artifact_evidence import GATES, _artifact_digests, build_bundle
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
