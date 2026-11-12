# Release evidence rehash gate — current candidate

**Date:** 2026-11-12  
**Candidate SHA:** `6f7cdf92487ab40a8a74af836f2128cd9ef8fc23`

## Result

The repository release-evidence suite passed **31/31 tests**:

```text
python -m pytest -q tests/test_release_evidence.py
```

The suite verifies exact artifact digest requirements, post-receipt byte
mutation detection, missing artifacts, mixed candidate commits, duplicate gate
IDs, profile selection and fail-closed release verdict behavior.

## Boundary

This is repository-local evidence for the existing release-evidence contract;
it is not a release verdict. The broader RTEST-015 proposal still calls for an
independent artifact-root verifier with explicit path confinement and symlink
negative cases. Those cases are not claimed by this receipt, and the 10-gate,
candidate-bound release aggregation remains open.

