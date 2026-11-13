# P1.8 — Durable project-archive idempotency

Date: 2026-11-13  
Status: PASS for SQLite reference storage and PostgreSQL implementation parity.

## Implementation

- Added a versioned SQLite migration for `project_archive_idempotency`.
- Added the equivalent PostgreSQL table and transactional lookup/insert path.
- Archive mutation now serializes on the durable store transaction.
- Reusing the same key for the same project is a successful replay.
- Reusing a key for another project is a stable `409 conflict`.
- The HTTP route passes the trimmed key into the application service; the header is not merely observed and discarded.

## Evidence

- Focused HTTP archive, service, storage, and bundle regression: **93 passed, 7 deselected**.
- Coverage includes missing key (`400`), first archive, replay after a new service/store instance, key-target conflict (`409`), and two concurrent SQLite callers where exactly one performs the transition and the other replays.
- Ruff across changed storage, service, control-plane, and test files: **clean**.

## Boundary

PostgreSQL live execution was not available in this local runner; its schema and transactional adapter path are implemented and remain subject to the repository's PostgreSQL real-provider lane. Public v1 release qualification remains unchanged.

## Progress

- P1 archive/idempotency implementation slice: **100% of this slice evidenced**.
- Official Public v1 denominator: **0/13 active families, 0%, NO-GO**.
