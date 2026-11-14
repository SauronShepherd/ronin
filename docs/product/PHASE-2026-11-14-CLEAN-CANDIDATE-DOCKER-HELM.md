# Clean candidate Docker/Helm qualification

Date: 2026-11-14  
Candidate: `8b9b677edc2eddc43a9f594e48438204a6365bb5`  
Mode: **CLEAN-CANDIDATE QUALIFICATION**  
Policy: manual qualification only; GitHub Actions is intentionally absent.

## Docker gate

The official Docker qualification script ran from a detached clean worktree.

- **27 passed, 0 skipped, 0 failed** in 234.78s.
- Strict v0.1 acceptance: **15/15**, `strict_success=true`.
- Image: `sha256:35e6f31cd908070cbcfc21fdb30c11c49a9ed3455e3d48ac308f3e070fd33ebb`.
- PostgreSQL, Docker worker, Floci/S3, Azurite/Azure and the frozen v0.1
  journey all executed successfully.
- Evidence: `%TEMP%\ronin-docker-clean-20261114-8b9b677`.

## Helm/kind gate

The official Helm qualification script consumed the Docker receipt and exact
image digest from the same clean candidate.

- Helm `v4.3.1`; kind cluster created and cleaned successfully.
- Lint, Secret boundary, install, readiness, upgrade revision 2, rollback to
  revision 1, health/API/Studio, persistent job and restart persistence all
  passed.
- Evidence: `%TEMP%\ronin-helm-clean-20261114-8b9b677`.

## Qualification boundary

These are clean-candidate infrastructure receipts, not a complete Public v1
release approval. Family journeys, provider matrix, visual review, legal/
license decisions, aggregate provenance and release governance remain open.
The official ledger remains **0/13 (0%), NO-GO**.
