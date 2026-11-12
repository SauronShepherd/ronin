# Qualification receipt — appliance backup/restore real

- Date: 2026-11-12
- Source checkout before receipt commit: `59ee065a38e577831abb4b3384257d12183a8651`
- Test: `tests/integration/test_postgres_appliance_backup_real.py`
- Result: **PASS — 1 passed, 0 skipped, 0 failed** (`42.83s`).
- Runtime: Docker Desktop Linux engine, PostgreSQL `16.4-alpine`, Ronin image built from this checkout with immutable image ID `sha256:b2e424c872e368010f5531b403d3df8af5728cf35d3efcab54fe0ec1d959850f`.
- Scope: isolated Compose project with temporary credentials; a PostgreSQL row and local artifact/evidence files were written before backup, changed after backup, then restored from the appliance bundle.
- Assertions: PostgreSQL returned only the pre-backup row; both local files returned their pre-backup bytes; bundle manifest, PostgreSQL sidecar checksum and data-tree inventory were present and validated.
- Cleanup: the test removed only its random Compose project and volumes.
- Qualification boundary: this closes the real local Compose round-trip diagnostic for the current checkout. It does not qualify external object-store recovery, upgrade/rollback rehearsal, supported-platform coverage, or Public v1 as a whole.
