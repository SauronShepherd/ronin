# Phase receipt — manual packaging diagnostic

## Status

**PASS — DIRTY-WORKTREE DIAGNOSTIC** for local package construction and archive
integrity.

## Evidence

- Command: `python -m build --wheel --sdist --outdir .tmp/manual-dist`.
- Wheel: `ronin_studio-0.0.0-py3-none-any.whl`, ZIP integrity check passed,
  SHA-256 `5325FFFDD99770088ADDFD43DED818A37E715464C7FAA1F7442E3EC785B0915A`.
- Sdist: `ronin_studio-0.0.0.tar.gz`, TAR listing/integrity check passed,
  SHA-256 `C0E05DD4C2F9EE169E051E6306079C102625061861976E82182E3134BA8BA65F`.
- The release-artifact verifier was invoked correctly as
  `python -m tools.verify_release_artifacts --help`; no release bundle was
  asserted because no clean artifact-identity manifest was supplied.

## Boundary

The checkout contains user-owned/untracked artifacts, so this is not a clean
candidate identity or publication approval. No registry upload was performed.
Public v1 remains **0/13 active families, 0%, NO-GO**.
