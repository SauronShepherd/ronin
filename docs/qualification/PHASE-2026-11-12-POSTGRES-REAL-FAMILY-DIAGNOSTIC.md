# Qualification receipt — PostgreSQL real family diagnostic

- Date: 2026-11-12
- Source checkout: `c759727283b3f4ce38645ab9d343da8134c2a6d5`
- Runner: `tools/run_postgres_test_suite.ps1 -TestFilter postgres`.
- Runtime: isolated `postgres:16.4-alpine`, loopback port allocated by the runner; credentials were generated per run and redacted from the transcript.
- Result: **111 passed, 1 skipped, 0 failed**, 4503 deselected, in `159.09s`.
- The selected real PostgreSQL coverage exercised scheduler leases/cancellation/outbox/replay, connector checkpoints and watermarks, catalog/quality/audit stores, workflow and ML Bundle atomicity, job-store lifecycle, data-engineering revisions, retention barriers and local composed HTTP. The only selected skip was the Docker-gated appliance test, intentionally outside this runner; two unrelated collection skips were reported separately.
- Cleanup: the runner removed its isolated PostgreSQL container and volumes successfully.
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-postgres-evidence-c759727`.
- Boundary: this is a filtered diagnostic, not the complete Python/PostgreSQL suite or a Public v1 family closure; provider/platform and end-to-end product criteria remain open.
