# Phase 2026-11-12 — SBOM and provenance candidate

## Scope

Generate and verify candidate-bound artifact identity, CycloneDX SBOM, local in-toto/SLSA provenance, and the combined supply-chain evidence record for the SDK artifacts produced by the isolated artifact phase.

## Candidate and artifacts

- Clean source candidate: `76ff81970f1cb0a3071f0c7ba047973fa0358214`
- Artifact identity: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-pyronin-identity-76ff819.json`
- Wheel: `pyronin-0.0.1a0-py3-none-any.whl`, SHA-256 `dd0ee355f489f67d610069d4a811d6665040540a78a860f80e61f008bc3b2ae5`
- sdist: `pyronin-0.0.1a0.tar.gz`, SHA-256 `926e12165ed9274c672fc7900936dcc5ce8a2f7668adb90ed085181d75583b9e`
- SBOM: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-pyronin-release-sbom-76ff819.json`
- Provenance: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-pyronin-provenance-76ff819.json`
- Combined evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-pyronin-supply-chain-76ff819.json`

## Gates

```text
python -m tools.generate_release_sbom --artifact-identity <identity> \
  --requirements-lock requirements-dev.lock --output <sbom>
python -m tools.generate_release_sbom --artifact-identity <identity> \
  --requirements-lock requirements-dev.lock --output <sbom> \
  --verify --expected-commit 76ff81970f1cb0a3071f0c7ba047973fa0358214
python -m tools.generate_release_provenance --artifact-identity <identity> \
  --build-command 'python -m tools.artifact_qualification' \
  --toolchain-json <toolchain> --output <provenance>
python -m tools.supply_chain_evidence --commit 76ff81970f1cb0a3071f0c7ba047973fa0358214 \
  --artifact-identity <identity> --sbom <sbom> --provenance <provenance> \
  --artifact-directory <artifact-dist> --output <combined-evidence>
```

Result: **PASS**. The verifier accepted the exact artifact digests, lock-derived dependency inventory, source commit, provenance subjects, and artifact bytes. The combined evidence record reports schema `ronin.supply-chain-evidence/v1` and provenance SHA-256 `4d6bed574821c4aab197d49ae4645e76f43bb195557c49899993b91255dd181f`.

## Qualification boundary

This closes the SDK SBOM/provenance phase. Container inventories and image security remain covered by the Docker/security gates; license and legal decisions remain human-controlled. Public v1 remains **0/13 (0%) — NO-GO**.

