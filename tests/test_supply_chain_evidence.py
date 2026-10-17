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
        json.dumps(
            {
                "commit": "abc",
                "subject": [{"name": "ronin.whl", "digest": {"sha256": "a" * 64}}],
            }
        ),
        encoding="utf-8",
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


def test_supply_chain_evidence_rejects_unrelated_sbom_subject(tmp_path: Path) -> None:
    identity, sbom, provenance = _fixtures(tmp_path)
    sbom.write_text(
        json.dumps({"spdxVersion": "SPDX-2.3", "packages": [{"name": "other.whl"}]}),
        encoding="utf-8",
    )

    with pytest.raises(SupplyChainEvidenceError, match="artifact subjects"):
        validate(commit="abc", artifact_identity=identity, sboms=[sbom], provenance=provenance)


def test_supply_chain_evidence_accepts_cyclonedx_and_hashes_every_sbom(tmp_path: Path) -> None:
    identity, _, provenance = _fixtures(tmp_path)
    sbom = tmp_path / "bom.json"
    sbom.write_text(
        json.dumps({"bomFormat": "CycloneDX", "components": [{"name": "ronin.whl"}]}),
        encoding="utf-8",
    )
    result = validate(commit="abc", artifact_identity=identity, sboms=[sbom], provenance=provenance)
    assert str(sbom) in result["sbom_digests"]


@pytest.mark.parametrize(
    ("identity_change", "message"),
    [
        (lambda value: value.update(schema="other"), "schema"),
        (lambda value: value.update(commit="def"), "commit"),
        (lambda value: value.update(artifacts=[]), "no artifacts"),
        (lambda value: value.update(artifacts=[None]), "invalid subject"),
        (
            lambda value: value.update(artifacts=[{"name": " ", "sha256": "a" * 64}]),
            "invalid digest",
        ),
        (
            lambda value: value.update(artifacts=[{"name": "x", "sha256": "g" * 64}]),
            "invalid digest",
        ),
    ],
)
def test_supply_chain_evidence_rejects_invalid_artifact_identity(
    tmp_path: Path, identity_change, message: str
) -> None:
    identity, sbom, provenance = _fixtures(tmp_path)
    value = json.loads(identity.read_text(encoding="utf-8"))
    identity_change(value)
    identity.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(SupplyChainEvidenceError, match=message):
        validate(commit="abc", artifact_identity=identity, sboms=[sbom], provenance=provenance)


def test_supply_chain_evidence_rejects_invalid_sbom_and_missing_evidence(tmp_path: Path) -> None:
    identity, sbom, provenance = _fixtures(tmp_path)
    with pytest.raises(SupplyChainEvidenceError, match="at least one SBOM"):
        validate(commit="abc", artifact_identity=identity, sboms=[], provenance=provenance)
    sbom.write_text(json.dumps({"packages": []}), encoding="utf-8")
    with pytest.raises(SupplyChainEvidenceError, match="neither SPDX nor CycloneDX"):
        validate(commit="abc", artifact_identity=identity, sboms=[sbom], provenance=provenance)
    sbom.write_text(json.dumps({"spdxVersion": "SPDX-2.3", "packages": [None]}), encoding="utf-8")
    with pytest.raises(SupplyChainEvidenceError, match="invalid component"):
        validate(commit="abc", artifact_identity=identity, sboms=[sbom], provenance=provenance)
    sbom.write_text(json.dumps({"spdxVersion": "SPDX-2.3", "packages": [{"name": "ronin.whl"}]}))
    with pytest.raises(SupplyChainEvidenceError, match="provenance evidence is required"):
        validate(commit="abc", artifact_identity=identity, sboms=[sbom])


@pytest.mark.parametrize(
    ("provenance_change", "message"),
    [
        (lambda value: value.update(commit="def"), "commit"),
        (lambda value: value.update(subject=[]), "no subjects"),
        (lambda value: value.update(subject=[None]), "invalid subject"),
        (lambda value: value.update(subject=[{"name": "ronin.whl"}]), "invalid subject digest"),
        (
            lambda value: value.update(
                subject=[{"name": "ronin.whl", "digest": {"sha256": "b" * 64}}]
            ),
            "do not match artifact identity",
        ),
    ],
)
def test_supply_chain_evidence_rejects_invalid_provenance_subjects(
    tmp_path: Path, provenance_change, message: str
) -> None:
    identity, sbom, provenance = _fixtures(tmp_path)
    value = json.loads(provenance.read_text(encoding="utf-8"))
    provenance_change(value)
    provenance.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(SupplyChainEvidenceError, match=message):
        validate(commit="abc", artifact_identity=identity, sboms=[sbom], provenance=provenance)


def test_supply_chain_evidence_json_loader_and_cli(tmp_path: Path, monkeypatch, capsys) -> None:
    from tools import supply_chain_evidence

    with pytest.raises(SupplyChainEvidenceError, match="cannot read JSON"):
        supply_chain_evidence._load(tmp_path / "missing.json")
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(SupplyChainEvidenceError, match="cannot read JSON"):
        supply_chain_evidence._load(malformed)
    malformed.write_text("[]", encoding="utf-8")
    with pytest.raises(SupplyChainEvidenceError, match="must be an object"):
        supply_chain_evidence._load(malformed)

    identity, sbom, provenance = _fixtures(tmp_path)
    output = tmp_path / "evidence.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "supply_chain_evidence",
            "--commit",
            "abc",
            "--artifact-identity",
            str(identity),
            "--sbom",
            str(sbom),
            "--provenance",
            str(provenance),
            "--output",
            str(output),
        ],
    )
    assert supply_chain_evidence.main() == 0
    assert json.loads(output.read_text(encoding="utf-8"))["commit"] == "abc"
    assert "supply-chain evidence invalid" not in capsys.readouterr().out
    monkeypatch.setattr(
        "sys.argv",
        [
            "supply_chain_evidence",
            "--commit",
            "bad",
            "--artifact-identity",
            str(identity),
            "--sbom",
            str(sbom),
            "--provenance",
            str(provenance),
            "--output",
            str(output),
        ],
    )
    assert supply_chain_evidence.main() == 2
    assert "supply-chain evidence invalid" in capsys.readouterr().out
