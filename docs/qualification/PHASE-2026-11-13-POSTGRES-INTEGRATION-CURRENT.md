# Qualification receipt — PostgreSQL integration lane current

- Date: 2026-11-13
- Source checkout: `fd17747fe1a37a1e5b1a57895a2f6819ee32e5cf`
- Runner: `tools/run_postgres_test_suite.ps1 -TestFilter postgres -AllowDirtyWorktree`.
- Runtime: isolated `postgres:16.4-alpine` container on a loopback-only ephemeral port.
- Result: **111 passed, 1 selected skip, 0 failed** out of 112 selected tests; 4,511 unrelated tests were deselected and 2 unrelated collection skips were reported.
- Coverage: real PostgreSQL stores, scheduler/workflow durability, ML registry, catalog, audit, connectors/checkpoints, quality, retention barriers, bundle atomicity, HTTP composition and contract boundaries.
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-postgres-current-fd17747-20261113060038`.
- Qualification boundary: this is a dirty-worktree diagnostic lane, not clean release evidence. The selected appliance test was skipped by its Docker opt-in guard and is covered separately by `PHASE-2026-11-13-POSTGRES-APPLIANCE-CURRENT.md`; full-family release qualification, external provider breadth, legal decisions and aggregate release gates remain open.
