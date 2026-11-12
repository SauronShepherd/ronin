# Phase receipt — backup/restore qualification — 2026-11-12

## Candidate/runtime

- Source tree candidate at start of qualification: `2c30c7e70d29af09f632607626481b30b6f3de85`.
- Ronin Docker image used by the real test: `sha256:8f5055382c366df3e8bc684b286ac66a55c6d46af79137b2287ba2203c00edd6`.
- PostgreSQL service: `postgres:16.4-alpine`, isolated Compose project and temporary data directory.

## Evidence

- Contract/negative/manifest coverage:
  `py -3 -m pytest -q tests/test_backup_manifest.py tests/test_ronin_appliance_backup.py tests/test_postgres_backup.py tests/test_compose_qualification.py`
  — `12 passed`.
- Real PostgreSQL + Ronin appliance backup/restore:
  `RONIN_REAL_DOCKER_QUALIFICATION=1 RONIN_DOCKER_QUALIFICATION_IMAGE=sha256:... py -3 -m pytest -q tests/integration/test_postgres_appliance_backup_real.py`
  — `1 passed in 24.40s`.
- The real journey wrote PostgreSQL state and local artifact/evidence files, created a backup bundle, mutated both stores, restored with the bundle, and verified the pre-backup database rows and files.

## Result

PASS for the implemented local Compose/PostgreSQL appliance backup/restore contract: `13/13` selected tests passed, with no skips in the executed set. The result is candidate/image-bound for this diagnostic run.

This does not by itself close the entire P14 family or Public V1 release: external object-store backup, migration/upgrade rollback, all provider profiles, clean candidate aggregation, and human release gates remain separate requirements. Official release-qualified progress remains `0/13 (0%)`.

## Cleanup

The integration test uses a unique temporary Compose project and removes its services/data in teardown.
