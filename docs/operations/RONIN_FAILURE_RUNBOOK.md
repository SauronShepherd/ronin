# Ronin failure and recovery runbook

This runbook is the operational boundary for the local/Compose reference
profile. It is intentionally explicit about evidence, authorization and
recovery; operators must not infer success from a process being alive.

## Triage invariants

1. Preserve the run, attempt, checkpoint and artifact identities before making
   changes.
2. Readiness, degraded and failed are different states; do not restart a
   healthy service as a first response.
3. Never delete a database, artifact root, checkpoint or audit ledger before a
   verified backup exists.
4. Mutation and emergency-disable actions require the normal typed grant and
   produce an audit event.

## Common incidents

| Symptom | First checks | Safe recovery |
|---|---|---|
| Stuck run | inspect run state, latest heartbeat, lease owner and events | allow bounded lease reclaim; cancel only with `job.cancel`; preserve evidence |
| Worker crash | inspect normalized attempt failure and lease expiry | restart worker, then resume/reclaim; verify artifact digests before execution |
| Database unavailable | readiness, migration version, connection health | stop writes, restore connectivity, rerun readiness and migration checks |
| Artifact corruption | compare stored digest with evidence reference | quarantine the artifact, restore from content-addressed backup, re-verify digest |
| Plugin degraded | plugin health/state and published contribution inventory | disable only the affected optional plugin; retain host and unrelated surfaces |
| Provider degraded | adapter state, bounded error code, circuit state | use an explicitly configured compatible provider or remain unavailable |
| Scheduler split-brain risk | leader/fence state and duplicate execution evidence | stop new scheduling, preserve fencing records, restore one authoritative leader |

## Backup and restore

For Compose, back up PostgreSQL using the repository backup utility and copy the
artifact directory with its digests. Restore into an isolated target, validate
schema/migration versions, then read representative workspaces, jobs, audit
events and ML records before cutover. Keep the original backup immutable.

## Emergency disable

Emergency disable is a controlled policy action, not a process kill shortcut.
Record actor, reason, scope and timestamp; block only the requested new work,
leave existing evidence readable, and require an explicit authorized action to
re-enable it.
