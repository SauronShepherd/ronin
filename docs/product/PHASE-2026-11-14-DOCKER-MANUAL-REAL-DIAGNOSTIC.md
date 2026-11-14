# Docker manual real qualification diagnostic

Date: 2026-11-14  
Source baseline: `25642ecb55e5679cb7bc826f9ece40d6a1865af1`  
Mode: **DIRTY-WORKTREE DIAGNOSTIC**  
Policy: manual qualification only; GitHub Actions is intentionally absent.

## Gate executed

```text
tools/run_docker_qualification.ps1 -EvidenceDirectory $e -AllowDirtyWorktree
```

Result: **27 passed, 0 skipped, 0 failed** in 201.33s.

Strict v0.1 acceptance: **15/15 passed**, `strict_success=true`.

The run built image digest:

```text
sha256:df186497d39af57330d2a13eaf508defc0c2422047d688a965bf682f0dd089ba
```

It exercised PostgreSQL-backed journeys, Docker worker execution/isolation,
process kill and lease reclamation, backup/restore, Floci S3, Azurite Azure
Blob, S3 sink retry, idempotent replay, evidence, SDK/CLI round-trip and
durable cancellation. Evidence is stored outside the checkout at:
`%TEMP%\ronin-docker-manual-20261114-25642ec`.

Because user-owned untracked artifacts remain in the worktree, this is not
clean-candidate release evidence. The official ledger remains **0/13 (0%),
NO-GO**.
