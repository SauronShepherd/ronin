# RTEST-015 — confined release-artifact verifier

**Date:** 2026-11-12  
**Candidate SHA:** `3c524e5633cf9dab59ea2c24b65b42bf1b3b1222`

## Implementation

Added `tools/verify_release_artifacts.py`, an independent fail-closed
verifier for a release-evidence bundle and an explicit sandbox root. It:

- accepts only relative artifact paths;
- rejects absolute paths, `.`/`..` components and path escapes;
- rejects symlinks in every path component;
- requires regular files;
- streams SHA-256 bytes and compares them to the declared digest;
- reuses the canonical release-evidence schema validation before reading files;
- emits a typed JSON verification report or exits non-zero on any failure.

## Qualification

Commands:

```text
python -m pytest -q tests/test_release_evidence.py tests/test_verify_release_artifacts.py
python -m ruff check tools/verify_release_artifacts.py tests/test_verify_release_artifacts.py
```

Result: **37 passed, 1 skipped, 0 failed** and Ruff clean. The skip is the
symlink negative on this Windows host, where symlinks are unavailable; the
implementation branch is covered and will execute on a POSIX runner.

The focused verifier tests cover valid rehash, absolute/traversal/dot-path
rejection, symlink rejection, and mutated-byte rejection. The existing release
evidence suite also covers post-receipt mutation and missing artifact failure.

## Boundary

This closes the OSS implementation and focused qualification of the verifier,
not the complete release verdict. Candidate artifact materialization, all
10/10 release gates, provenance/SBOM binding and human/legal approval remain
separate requirements.

