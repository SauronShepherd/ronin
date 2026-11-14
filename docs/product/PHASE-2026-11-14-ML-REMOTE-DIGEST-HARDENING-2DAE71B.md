# Phase 2026-11-14 — ML remote artifact digest hardening

## Scope

Close RTEST-BLK-027's reproducible contract gap: the remote ML adapter
contract requires a lowercase SHA-256 digest whenever an artifact reference and
digest are supplied, but validation previously enforced the full digest only
for `succeeded` results.

## Change

`RemoteTrainingResult.__post_init__` now validates the `sha256:` namespace and
exact 64-character lowercase hexadecimal payload for every non-empty artifact
digest, regardless of status (`queued`, `running`, `succeeded`, `failed` or
`cancelled`). The contract regression now covers malformed non-success states
and uses a valid digest in the queued identity test.

## Evidence

- Focused contract test: **10 passed**.
- Related ML regression (`remote_contract`, candidate hardening,
  orchestration, end-to-end registry and drift): **39 passed**.
- Ruff format check: passed.
- Ruff lint: passed.
- `git diff --check`: passed.
- Candidate source before receipt commit: `2dae71bc23966d77ba826ab4f2442f7f41866711`.

## Result

Technical ML contract phase **PASS**. Public v1 remains `0/13`, `0%`, `NO-GO`;
provider certification and the complete installed ML family journey remain
separate release gates.
