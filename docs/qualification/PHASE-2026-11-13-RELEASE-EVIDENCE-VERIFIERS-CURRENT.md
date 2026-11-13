# Release evidence and artifact verifiers — current candidate

**Date:** 2026-11-13  
**Candidate SHA:** `aac6adc1e404e4d9010965792052748f1aa985d2`

## Gate

```text
python -m pytest -q tests/test_release_evidence.py tests/test_verify_release_artifacts.py tests/test_release_case_inventory.py tests/test_release_supply_chain_generators.py
```

Result: **103 passed, 1 skipped, 0 failed** in 33.18 seconds.

The suite covers release-evidence validation/merge/verdict contracts, confined
artifact paths, traversal/symlink/mutation and digest checks, release case
inventory and supply-chain evidence generators. The one skip is the Windows
symlink capability test and is not counted as a pass.

## Boundary

This qualifies the verifier and evidence-contract tooling only. It does not
create a complete `release_required` aggregate, legal approval, provider
certification or 13-family Public v1 verdict. Public v1 remains **0/13 (0%) —
NO-GO**.
