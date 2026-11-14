# Phase receipt — clean artifact identity

## Status

**PASS — CLEAN CANDIDATE DIAGNOSTIC** for candidate-bound Python artifacts.

## Scope

- Phase: manual release evidence / artifact identity.
- Candidate SHA: `3d17c794a2f0b2072f7118a0f049cfa7bcaacbbd`.
- Execution environment: temporary detached worktree at the candidate SHA,
  with a clean tracked tree.
- No GitHub Actions, registry upload, or release publication was used.

## Evidence

- `python -m build --wheel --sdist` completed successfully.
- Wheel ZIP integrity check passed:
  `ronin_studio-0.0.0-py3-none-any.whl`, 2,713,202 bytes,
  SHA-256 `c27f5bbb9459d2dbbef9807364b53dc29781abbb50aabd8aa0553e574f7ab42f`.
- Sdist TAR listing/integrity check passed:
  `ronin_studio-0.0.0.tar.gz`, 2,936,541 bytes,
  SHA-256 `5be460fcc7f1c85d7d62dd63293d51496cfce950a17f4840fb981965ba358f3b`.
- `tools.artifact_identity` produced schema
  `ronin.artifact-identity/v1`, bound to the candidate SHA and both artifact
  digests.

## Boundary

The manifest is evidence for the candidate artifacts only. No registry
publication was performed or implied. Public v1 remains **0/13 active
families, 0%, NO-GO**.
