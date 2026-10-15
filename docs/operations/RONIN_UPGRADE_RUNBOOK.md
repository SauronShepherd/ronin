# Ronin upgrade and migration runbook

Upgrades are forward-only unless the release explicitly documents a rollback
boundary. Do not start an application against a newer schema without a backup.

1. Record the candidate image/package digest and current schema versions.
2. Create and verify a clean deployment backup before stopping writes. The
   supported local API is:

   ```python
   from studio_storage import backup_deployment

   backup_deployment(database, artifacts, backup_dir)
   ```

   The resulting manifest covers the SQLite metadata database and every
   artifact digest. PostgreSQL deployments must use the repository backup
   helper (or the equivalent `pg_dump --format=custom`) and retain its
   adjacent `.sha256` sidecar together with the artifact-store inventory and
   checksums defined by the deployment profile.
3. Verify PostgreSQL and artifact backups, including checksums and retention.
4. Stop or drain writes according to the deployment profile.
5. Apply migrations transactionally and confirm the expected migration registry.
6. Start the candidate and run readiness, route-consistency and representative
   smoke checks.
7. Verify workspace/project identities, job evidence, audit records, artifact
   reads and representative ML/quality records.
8. Retain the pre-upgrade backup and evidence; never rebuild the qualified
   candidate between qualification and publication.

The compatibility window is the interval in which the previous candidate can
remain stopped while the new candidate is validated against the migrated
schema; applications must not write to a schema newer than the candidate they
run. Rollback is limited to restoring the verified backup into an isolated
clean deployment:

```python
from studio_storage import restore_deployment

restore_deployment(backup_dir, clean_database, clean_artifacts)
```

Destructive reverse migrations are not assumed safe. Any failed step leaves
the deployment in maintenance mode until the operator has a verified target
and an auditable cutover decision.
