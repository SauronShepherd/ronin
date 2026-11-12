# Phase receipt — QueryFlux worker reclaim/recovery — 2026-11-12

## Finding and correction

The first recovery attempt exposed a real integration defect: the worker sent
the QueryFlux scheduler target through notebook preparation, producing
`worker.preparation.error` before the injected QueryFlux runner could execute.
The target is now explicitly classified as a scheduler workload and requires a
composed `queryflux_runner`, avoiding notebook preparation and preserving the
fail-closed boundary.

## Verification

```text
test_restart_reclaims_queryflux_job_and_executes_once: passed
worker runtime suite: 14 passed
```

The test seeds a durable QueryFlux Job/Run, leaves an expired claim from the
first worker identity, starts the replacement worker at the post-expiry clock,
and verifies one QueryFlux runner invocation, reclaimed run identity and a
single succeeded durable job.

## Decision

PASS for durable worker reclaim and QueryFlux scheduler routing. A separate
OS-process SIGKILL gate with the real provider remains the final recovery
qualification. Public v1 remains **0/13 (0%) — NO-GO**.
