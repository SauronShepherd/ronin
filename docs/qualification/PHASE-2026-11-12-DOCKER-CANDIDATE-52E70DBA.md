# Phase receipt — Docker exact candidate refresh — 2026-11-12

## Candidate and image

- Source: `52e70dbab3550db4d762d9897d30a17082198abd`
- Worktree: clean detached candidate
- Image: `sha256:7f5d5f4717cb24f43e58eee2fedd1eb8d49c85524f13edb037ae1a3dc5805951`
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-docker-current-evidence-20261112184843`

## Gate result

```text
Docker integration acceptance: PASS; 27 tests, 0 skipped, 0 failed
v0.1 acceptance: live=15 passed=15 skipped=0 xfailed=0 failed=0
strict_success=true
DOCKER_EXIT=0
```

The candidate-bound run covered PostgreSQL workers/recovery, Docker isolation
and resource limits, backup/restore, Floci/S3, Azurite/Azure Blob and the full
strict v0.1 journey. JUnit, strict JSON, logs and timing output are retained
outside the checkout.

## Decision

PASS for the exact candidate Docker gates. Public v1 remains **0/13 (0%) —
NO-GO** pending family-specific and release-governance gates.
