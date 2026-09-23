import json
from pathlib import Path

import pytest

from tools.supply_chain_evidence import SupplyChainEvidenceError, validate


def _fixtures(tmp_path: Path) -> tuple[Path, Path, Path]:
    identity = tmp_path / "identity.json"
    identity.write_text(
        json.dumps(
            {
                "schema": "ronin.artifact-identity/v1",
                "commit": "abc",
                "artifacts": [{"name": "ronin.whl", "sha256": "a" * 64}],
            }
        ),
        encoding="utf-8",
    )
    sbom = tmp_path / "sbom.json"
    sbom.write_text(
        json.dumps({"spdxVersion": "SPDX-2.3", "packages": [{"name": "ronin.whl"}]}),
        encoding="utf-8",
    )
    provenance = tmp_path / "provenance.json"
    provenance.write_text(
        json.dumps({"commit": "abc", "subject": [{"name": "ronin.whl"}]}), encoding="utf-8"
    )
    return identity, sbom, provenance


def test_supply_chain_evidence_binds_candidate_and_all_inputs(tmp_path: Path) -> None:
    identity, sbom, provenance = _fixtures(tmp_path)
    result = validate(commit="abc", artifact_identity=identity, sboms=[sbom], provenance=provenance)
    assert result["schema"] == "ronin.supply-chain-evidence/v1"
    assert result["provenance_sha256"]


def test_supply_chain_evidence_rejects_stale_candidate(tmp_path: Path) -> None:
    identity, sbom, _ = _fixtures(tmp_path)
    with pytest.raises(SupplyChainEvidenceError, match="commit"):
        validate(commit="def", artifact_identity=identity, sboms=[sbom])
