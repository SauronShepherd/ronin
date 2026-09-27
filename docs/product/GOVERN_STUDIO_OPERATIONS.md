# Govern Studio Operations Runbook

The application SQLite adapter uses schema version 1 (`PRAGMA user_version`).
Opening a newer unsupported version fails closed; opening an unversioned v1
database creates the run and artifact tables and records the version.

## Operating rule

An artifact is usable only for the intended use recorded in its plan and only
after the required validation and policy gates have passed. A successful process
exit is not publication approval.

## Local run storage

The application service supports an injected `SqliteRunStore`. It persists the
authored plan, lifecycle status, generated rows, validation evidence, and the
idempotency key in one portable SQLite database. Reopening a service with the
same database recovers a run instead of silently starting a second one. The
default remains `InMemoryRunStore` for isolated tests and disposable sessions.

## Readiness checks

```text
plugin discovery = ready
required providers = available
storage migration = current
workspace policy = loaded
staging root = writable and isolated
job runtime = accepting leases
artifact store = readable
telemetry = emitting bounded dimensions
```

## Run inspection

Inspect in this order:

1. request and idempotency key;
2. plan fingerprint and version;
3. profile ids and expiry;
4. provider lock and resource estimate;
5. current run/attempt/lease;

## UI verification

Open `#synthetic` in the Ronin web shell. The Govern Studio panel submits a
plan to the plugin, displays the generated run, loads only formats whose
provider status is `ready`, and exports the selected table through the same
backend route. Optional Delta, Iceberg and Hudi providers remain intentionally
hidden from the writable export selector until their dependencies are present.
6. staged files and checksums;
7. expectation results;
8. policy decision and approval;
9. export receipt and destination verification;
10. cleanup status.

Never delete a failed run before preserving its receipt and evidence.

## Failure playbooks

### Provider unavailable

Pause new requests requiring the provider. Keep existing validated artifacts
readable. Do not silently switch provider because that changes the plan
fingerprint and utility behavior. Install or enable the exact locked provider,
run compatibility checks, then resume only if the provider lock matches.

### Lease lost or worker crash

The runtime must reject a commit with an old fencing token. Inspect staging,
attempt and last checkpoint. Reclaim only if the task declares resume support;
otherwise mark the attempt failed and create a new run. Never mark generated when
the final manifest was not atomically committed.

### Constraint exhaustion

Record attempted rows, rejected rows, repair count and the first safe diagnostic.
If severity is error, leave the candidate unpublishable. Change the constraint or
provider in a new plan version; do not mutate the old plan in place.

### Validation regression

Keep the candidate artifact immutable. Compare report fingerprints, provider lock,
profile fingerprint, expectation version and engine version. A changed threshold
creates a new report; it does not rewrite history.

### Policy denial

Return the stable denial code and remediation category, not internal policy source
or sensitive inputs. Preserve the decision id and policy version. An operator may
change policy only through the normal governance process.

### Partial export

Mark export `partial`, retain the validated source artifact, close the writer,
verify which files exist and remove staging only after evidence is captured. A
retry uses a new export attempt or a verified idempotent destination operation;
never append blindly.

### Corrupt artifact

Stop publication and mark the artifact suspect. Recompute checksums from the
staged/source representation, compare the manifest, and quarantine the output.
Restore the artifact from a known-good immutable copy or rerun generation from
the exact plan/provider lock. Record the remediation and revoke approvals tied to
the corrupt artifact.

### Emergency disable

Set the feature flag to off, stop accepting new mutating requests, allow safe
read/report operations, preserve active runs, and drain or cancel workers using
the normal cancellation protocol. Do not destroy artifacts or plugin tables.

## Recovery and migration

Before plugin migrations, create a storage recovery point. Apply expand changes,
run reconciliation, then activate reads/writes. For restore, validate plans,
runs, reports, approvals, exports and artifact references before redirecting the
application. A restore creates a candidate state; it is not an automatic cutover.

## Retention

Retention is evaluated independently for source profile, plan, report, artifact,
export and audit evidence. A report may be retained after an artifact expires.
Garbage collection requires a reference scan, dry-run output and an audit event.

## Telemetry rules

Allowed metric dimensions are bounded enums and operation classes. IDs belong in
trace attributes or structured logs with redaction. Never put raw values, source
paths, tokens, sample content or user-provided expressions in metrics.

Minimum alerts:

- failed runs above baseline;
- lease reclaim rate;
- constraint exhaustion;
- validation failures by dimension;
- policy denials;
- export verification failures;
- staging growth and cleanup lag;
- telemetry cardinality overflow.

## Release smoke

Use a tiny approved fixture and execute:

```text
request -> plan -> profile -> compile -> generate -> validate
        -> policy -> approval -> export -> verify -> receipt
```

Run one negative smoke for unauthorized destination or missing approval. The
release is healthy only when both positive and negative paths produce expected
evidence.
