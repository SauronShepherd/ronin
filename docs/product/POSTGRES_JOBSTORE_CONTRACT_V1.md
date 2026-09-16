# PostgreSQL JobStore contract

This document is the implementation boundary for PostgreSQL lifecycle
storage. `PostgresMetadataStore` is not a JobStore: metadata transactions do
not provide the lease, fencing, retry, event, result or evidence semantics
required by `studio_orchestrator.JobStore`.

## Required scope

The adapter is complete only when it implements every method in the
`JobStore` protocol and passes the same conformance suite as `SqliteJobStore`:

- idempotent job/run creation and conflict detection;
- job lookup and filter-bound keyset pagination;
- cancellation with pending/leased/running state transitions;
- atomic run claiming, attempt creation and lease expiry;
- owner/token fenced heartbeat and authoritative writes;
- contiguous execution events, cell results and evidence references;
- terminal attempt completion and job/run state propagation;
- expired-lease reclaim and crash replacement.

## Schema and transaction rules

The migration must create PostgreSQL-native equivalents of the lifecycle
tables (`jobs`, `runs`, `attempts`, execution events, cell results and
evidence), including the same uniqueness, foreign-key, state and monotonic
revision constraints as the SQLite schema. Timestamps are stored as UTC
instants with one canonical serialization at the domain boundary.

Every authoritative transition is one transaction. A worker write must lock
and verify the attempt row's owner, lease token, state and revision before
mutating it. A lost lease rolls back the complete transaction and raises the
same lease-loss error as SQLite. Job/run completion, event/result/evidence
publication and the required revision update are never split across commits.

Run claiming must select eligible pending runs with `FOR UPDATE SKIP LOCKED`,
then create the attempt and update the run/job state in that same transaction.
This is the PostgreSQL concurrency primitive; an unlocked `SELECT` followed by
an update is not an acceptable implementation.

## Cursor and compatibility rules

Job cursors use the existing versioned opaque cursor helpers and remain bound
to the complete filter scope (`project_id`, authorized `project_ids` and
state). A cursor from another scope must fail closed. Event cursors remain
bound to their run and preserve contiguous ordering across attempts. The
PostgreSQL adapter must not expose database surrogate keys as public identity.

## Delivery sequence

1. Add a versioned PostgreSQL lifecycle migration and schema verification.
2. Implement row conversion and idempotent create/get/list operations.
3. Implement cancel/claim/heartbeat with transaction-level fencing.
4. Implement events, cell results, evidence, completion and reclaim.
5. Run the shared JobStore conformance suite against PostgreSQL and SQLite.
6. Add concurrent multi-worker qualification, rollback/failure-injection tests,
   backup/restore evidence and Docker Compose integration.
7. The server wires `RONIN_POSTGRES_DSN` only after the adapter contract is
   implemented; initialization fails closed rather than silently falling back
   to SQLite.

Until all seven steps pass, the PostgreSQL JobStore remains implemented but
not fully qualified for release; production-readiness and multi-node HA claims
must remain out of scope.
