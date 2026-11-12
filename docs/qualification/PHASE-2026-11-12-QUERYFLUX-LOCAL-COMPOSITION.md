# Phase receipt — QueryFlux local durable composition — 2026-11-12

## Implemented

- Local composed server now injects the QueryFlux lifecycle store and the same
  `DurableExecutionService` submitter used by the control plane jobs.
- The worker command accepts explicit `RONIN_QUERYFLUX_URL` configuration and
  composes the QueryFlux provider, Trino-compatible transport, evidence stores
  and `QueryFluxWorkerRunner`.
- Without `RONIN_QUERYFLUX_URL`, the worker remains fail-closed for the target;
  no provider endpoint or credentials are inferred.

## Verification

```text
CLI/local-composition/plugin/worker tests: 70 passed
compileall: passed
git diff --check: passed
```

## Decision

PASS for local durable composition wiring. The next gate must exercise the
full process boundary: submit through the local API, start the worker with the
explicit provider URL, restart it during/after a claim, and verify no duplicate
execution. Public v1 remains **0/13 (0%) — NO-GO**.
