# Phase receipt — QueryFlux durable job identity — 2026-11-12

## Implemented

- Added deterministic `QueryFluxExecutionPlan` generation for the durable job
  and run pair.
- Bound the idempotency key to workspace, project, `run_id` and `attempt_id`.
- Persistable canonical parameters include engine, translation policy, bounded
  result limits and request payload for later worker dispatch.
- Added validation for non-empty scoped identifiers and positive limits.

## Verification

```text
QueryFlux plan/lifecycle/plugin focused tests: 28 passed
git diff --check: passed
```

## Decision

PASS for deterministic durable identity and bounded request planning. The
worker dispatch, restart recovery and real asynchronous execution remain
outstanding; this receipt does not claim QueryFlux Public v1 qualification.
Public v1 remains **0/13 (0%) — NO-GO**.
