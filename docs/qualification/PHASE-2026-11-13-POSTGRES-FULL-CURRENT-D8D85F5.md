# Qualification receipt — full Python/PostgreSQL current suite

- Date: 2026-11-13
- Source checkout: `d8d85f52acec6b5f7ef02d75ee17af9297a458c8`
- Qualification mode: **DIRTY-WORKTREE DIAGNOSTIC**; preserved user artifacts and the user-owned public status edit were present.
- Service profile: isolated PostgreSQL 16.4 Alpine.
- Scope: all non-performance Python tests in `tests` and `packages/pyronin/tests`, including PostgreSQL-enabled cases.
- Result: **4,597 passed, 30 skipped, 0 failed** in 546.85 seconds.
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-postgres-full-fixed-20261113080632`.
- Cleanup: runner completed its PostgreSQL cleanup successfully.
- Notable skips: Docker opt-in, external S3/Azurite/Trino/OTLP/SDP providers, Windows symlink privileges and POSIX-only process semantics.
- Boundary: this is complete current Python/PostgreSQL diagnostic evidence, not a clean-candidate release gate; provider-specific and end-to-end family journeys remain separately required.
