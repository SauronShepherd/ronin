# Phase receipt — Docker manual qualification diagnostic

## Status

**PASS — DIRTY-WORKTREE DIAGNOSTIC**. This is strong local runtime evidence,
but it is not clean-candidate release evidence because user-owned untracked
artifacts were present in the checkout.

## Evidence

- Manual command: `tools/run_docker_qualification.ps1 -EvidenceDirectory <external> -AllowDirtyWorktree`.
- Source SHA used by the script: `e978b02a200cd9aa46d1381c6b91d6347e653466`.
- Docker image digest: `sha256:209514decaa20818c198e4be8f57d9e779cf442a3d751d23d520309ffbca3c41`.
- Real Docker qualification: **27 passed, 0 skipped, 0 failed** in 200.80 s.
- Strict frozen v0.1 acceptance: **15/15 passed**, `strict_success=true`.
- Services exercised: PostgreSQL 16.4, real Docker worker, Floci/S3 and Azurite/Azure Blob.
- Evidence directory: `C:\Users\angel.alvarez\Documents\ChatGPT\ronin-docker-evidence-20261114-1`.

## Boundary

The dirty-worktree classification is intentional; no clean-candidate claim is
made. This runtime evidence does not qualify a Public v1 family by itself.
Public v1 remains **0/13 active families, 0%, NO-GO**, with
`release_status=incomplete` and `qualification_status=qualification_pending`.
