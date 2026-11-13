# Qualification receipt — full Docker integration and v0.1 acceptance

- Date: 2026-11-13
- Source checkout: `56fda729048809db097cdebbee4639604e4901a2`
- Qualification mode: **DIRTY-WORKTREE DIAGNOSTIC**; preserved user artifacts and the user-owned public status edit were present.
- Image: built from this checkout, `ronin:qualification`, digest `sha256:ebd7f76677f2b29a2812533ec54f88edd340349a53a33b659f6f7df111f6fd03`.
- Result: **27 passed, 0 skipped, 0 failed** in 210.02 seconds.
- Strict frozen v0.1 acceptance: **15/15 passed, 0 skipped, 0 failed, 0 errors, 0 missing, 0 unexpected**.
- Fixtures: isolated PostgreSQL 16.4, Docker worker/runtime, Floci S3-compatible storage, and Azurite Azure Blob.
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-docker-full-20261113082343`.
- Cleanup: runner completed its service/container cleanup successfully.
- Boundary: this is current exact-HEAD diagnostic evidence, not clean-candidate release evidence; it does not by itself qualify all 13 Public v1 families.
