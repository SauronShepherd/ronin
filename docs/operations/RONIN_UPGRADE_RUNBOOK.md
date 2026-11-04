# Ronin upgrade and migration runbook

Upgrades are forward-only unless the release explicitly documents a rollback
boundary. Do not start an application against a newer schema without a backup.

1. Record the candidate image/package digest and current schema versions.
2. Create and verify a clean deployment backup before stopping writes. For the
   Docker Compose appliance with local artifacts, use the appliance bundle:

   ```powershell
   python -m tools.ronin_appliance_backup --backup-appliance ./.ronin/backups/appliance-before-upgrade
   ```

   It quiesces Compose writers and stores a PostgreSQL dump, the full
   `/var/lib/ronin` local-data volume, SHA-256 inventory and manifest in a new
   destination directory. A PostgreSQL-only dump does not include artifacts or
   execution evidence. S3-backed artifacts require a separate provider backup;
   the local bundle rejects that configuration. The supported local SQLite
   API is:

   ```python
   from studio_storage import backup_deployment

   backup_deployment(database, artifacts, backup_dir)
   ```

   The resulting manifest covers the SQLite metadata database and every
   artifact digest. For PostgreSQL, the appliance bundle above covers local
   data; a standalone PostgreSQL dump is database-only and must be accompanied
   by its adjacent `.sha256` sidecar and a separate artifact-store backup.
3. Verify the appliance bundle manifest, PostgreSQL sidecar, local-data
   inventory, and provider-specific object-store backup before proceeding. If
   rollback is required for a local Compose appliance, restore the verified
   bundle into the intended deployment; this replaces its database and local
   data volume and requires explicit `--force`:

   ```powershell
   python -m tools.ronin_appliance_backup --restore-appliance ./.ronin/backups/appliance-before-upgrade --force
   ```

   Bundle checksums are validated before writers stop. If restore fails after
   quiescing, services remain stopped in maintenance mode until the operator
   recovers a verified state.
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
