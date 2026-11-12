# Phase receipt — QueryFlux real worker runner — 2026-11-12

## Implemented

- Added `QueryFluxWorkerRunner`, backed by the existing bounded
  `execute_query` orchestration and provider/transport interfaces.
- The runner persists `queued → running → succeeded/failed/cancelled` in the
  SQLite/PostgreSQL-compatible lifecycle store.
- Cancellation is checked before each provider poll and delegates
  `transport.cancel(handle)` before persisting `cancelled` or a safe failure.
- Durable evidence and its project/run/attempt reference are committed before
  the terminal lifecycle transition is exposed.
- Scheduler dispatch now has an injectable production runner boundary.

## Verification

```text
QueryFlux execution, runner, lifecycle and scheduler tests: 41 passed
git diff --check: passed
```

## Decision

PASS for the real runner orchestration and terminal evidence boundary. Full
process-restart recovery and an end-to-end PostgreSQL/Trino asynchronous gate
remain outstanding. Public v1 remains **0/13 (0%) — NO-GO**.
