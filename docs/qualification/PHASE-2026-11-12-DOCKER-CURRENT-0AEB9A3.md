# Docker and strict acceptance qualification — current candidate

**Date:** 2026-11-12  
**Candidate SHA:** `0aeb9a34e709b7a6b0879f4616ef98c47f608b28`  
**Image:** `ronin:qualification-0aeb9a3`  
**Image ID:** `sha256:e264ae1cb84a65e4785b60a7d855c4afe47f678343ac19848b63e39b5d44ce3b`

## Gates

Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-docker-qualification-0aeb9a3-20261112221954`

- Docker integration acceptance: **27 passed, 0 skipped, 0 failed**.
- Strict frozen v0.1 acceptance: **15/15 passed**, 0 skipped, 0 xfailed,
  0 failed, 0 errors, 0 missing, 0 unexpected.
- Real fixtures: PostgreSQL, Docker worker, Floci/S3 and Azurite/Azure.
- Covered recovery: worker SIGKILL/reclaim, lease restart, cancellation and
  PostgreSQL/local-volume appliance backup/restore.
- Cleanup completed by the runner.

## Decision

Docker and strict v0.1 qualification phase: **PASS** for this candidate.

This evidence does not by itself close the 13 Public v1 families or the
human/legal/provider/release-governance gates. Public v1 remains **0/13 (0%) —
NO-GO**.
