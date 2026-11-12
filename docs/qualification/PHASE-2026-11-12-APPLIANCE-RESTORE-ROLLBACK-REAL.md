# Qualification receipt — appliance restore rollback hardening

- Date: 2026-11-12
- Source checkout: `7d5a20b5858b930fd5cc46a4332d514e5254ad6f`
- Runtime image built from that checkout: `sha256:6b4a991497516b584be02e90ad521846b0353504d592d315376dfeeab5c35602`.
- Real gate: `tests/integration/test_postgres_appliance_backup_real.py` — **1 passed, 0 skipped, 0 failed** (`23.86s`).
- Unit regression: `tests/test_ronin_appliance_backup.py` — **4 passed**.
- Change qualified: appliance restore snapshots the pre-restore local volume while writers are quiesced; if PostgreSQL restore fails, the previous data generation is restored and writers remain stopped. Writers resume only after both data and database restore succeed.
- Real assertions: the isolated Compose PostgreSQL row and local artifact/evidence files were changed after backup and returned to their pre-backup values from the bundle.
- Boundary: this improves and requalifies local Compose recovery. It does not close external object-store recovery, upgrade rehearsal, supported-platform coverage, or the complete P14/Public v1 family.
