# P2/P4/P5/P8/P14 — Docker integration qualification

**Date:** 2026-11-12  
**Candidate SHA:** `6b96e63acc16ec4bf237ff966e1c141480efc97d`  
**Runner:** `tools/run_docker_qualification.ps1` from a clean detached worktree  
**Evidence:** `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-docker-qualification-6b96e63`

## Immutable environment

- Ronin image: `ronin:qualification-6b96e63`
- Image digest: `sha256:481e40fd185d501f92c7ed086ae8b7d207b15a5b87cb74670db1cf143b24e2a9`
- PostgreSQL, Docker worker, Floci/S3 and Azurite/Azure services were isolated
  and cleaned up successfully.

## Results

- Docker integration acceptance: **27 passed, 0 skipped, 0 failed** in 197.62s.
- Strict v0.1 acceptance: **15/15 passed**, 0 skipped, 0 xfailed, 0 failed.
- Real coverage included worker crash/reclaim, Docker isolation/resource limits,
  Azure Blob discovery/read/replay, S3 sink/retry, durable ML S3 round-trip,
  PostgreSQL-backed execution, appliance backup/restore, SDK/CLI round-trip,
  restart/lease expiry, idempotency, cancellation and terminal evidence.

## Boundary

This is strong candidate-bound Docker/provider evidence, not a complete Public
v1 release verdict. Broader family journeys, external provider breadth,
license/legal approval, complete release-required aggregation and human gates
remain open. Public v1 remains **0/13 (0%) — NO-GO**.

