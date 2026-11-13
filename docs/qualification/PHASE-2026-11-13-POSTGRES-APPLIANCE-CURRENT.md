# Qualification receipt — PostgreSQL appliance backup/restore current

- Date: 2026-11-13
- Source checkout: `b357f538ddc6830bd482656b5923c0a51434ce5e`
- Worker image: `sha256:d6786037890250e502a3dd1e6900044f5079a7594052e7011d412937f56131a8`
- Test: `tests/integration/test_postgres_appliance_backup_real.py` with `RONIN_REAL_DOCKER_QUALIFICATION=1`.
- Runtime: isolated Docker Compose PostgreSQL `16.4-alpine` and Ronin service, with temporary qualification data.
- Result: **1 passed, 0 skipped, 0 failed** in 23.18 seconds.
- Scope: PostgreSQL state and local artifact/evidence volumes were backed up, mutated, restored, and verified against the pre-backup values; bundle/checksum/data-tree assertions passed.
- Boundary: this closes the current appliance backup/restore lane; full PostgreSQL provider breadth, operational recovery matrix, release aggregation, license decisions and complete family qualification remain open.
