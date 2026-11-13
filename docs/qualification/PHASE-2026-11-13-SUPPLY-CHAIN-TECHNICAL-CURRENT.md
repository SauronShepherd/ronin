# Technical supply-chain contracts — current candidate

**Date:** 2026-11-13  
**Candidate SHA:** `730ed6fc0149e374aca30bd5d187bc64ab2f1c8d`

## Gate

```text
python -m pytest -q tests/test_artifact_identity.py tests/test_container_sbom_boundaries.py tests/test_container_sbom.py tests/test_ml_provenance.py tests/test_release_supply_chain_generators.py tests/test_sbom_provenance.py tests/test_supply_chain_evidence.py
```

Result: **148 passed, 0 failed** in 77.20 seconds.

The suite covers artifact identity, container SBOM binding boundaries, ML and
release provenance, SBOM generation, digest/candidate matching and supply-chain
evidence validation.

## Boundary

This is automated technical supply-chain evidence. It does not close the
separate license/NOTICE human-review gate, external security acceptance or the
complete release-required aggregation. Public v1 remains **0/13 (0%) — NO-GO**.
