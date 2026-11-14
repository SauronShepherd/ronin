# Container SBOM and provenance qualification — current candidate

Date: 2026-11-14  
Candidate: `61ea62910472a10c798e302207d06677dd8c5696`  
Policy: local/manual qualification only; GitHub Actions is intentionally absent.

## Gate executed

Trivy **0.76.1** generated CycloneDX 1.7 SBOMs from the exact saved runtime and
probe image archives. Both SBOMs were bound with `tools.bind_container_sbom` to
the artifact identity and verified by `tools.supply_chain_evidence` with
`--require-container-inventory`.

Result:

- Runtime image: reference `ronin:qualification`, 59 OS packages.
- Probe image: reference `ronin:qualification-probe`, 56 OS packages.
- Both container SBOM bindings: **PASS**.
- Application SBOM and local provenance: **PASS**.
- Combined evidence schema: `ronin.supply-chain-evidence/v1`.
- Combined evidence: `C:\Users\angel.alvarez\Downloads\ronin-container-supply-61ea629\combined-evidence.json`.
- Container inventory count: **2**.
- Trivy vulnerability scan exit status: **0** for both image archives.

## Qualification boundary

This closes the technical container SBOM/provenance slice. The identity was
generated through the pure manifest builder because pre-existing untracked user
artifacts keep the shared checkout dirty; it is therefore diagnostic rather
than clean-candidate release evidence. License/legal review and complete Public
v1 family qualification remain open. The official ledger remains **0/13 (0%),
NO-GO**.
