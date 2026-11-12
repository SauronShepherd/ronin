# Phase receipt — QueryFlux asynchronous create contract — 2026-11-12

## Implemented

- Added `POST /v1/workspaces/{workspace_id}/projects/{project_id}/data-engineering/queryflux/executions`.
- Creation validates the bounded request, persists the lifecycle record before
  dispatch and derives a deterministic durable Job/Run plan.
- Repeated creation for the same workspace/project/run/attempt returns the
  existing lifecycle and invokes the worker submitter only once.
- The route fails closed when the host has no durable execution store and job
  submitter; it never reports a queued execution backed only by memory.
- OpenAPI, route inventory and snapshot are synchronized.

## Verification

```text
route consistency: passed for 199 operations
focused tests: 33 passed
OpenAPI snapshot: 340f0e7091802abc7864ab0081618e8aa7dd8543179842def235e39b846f04d9
```

## Decision

PASS for the asynchronous create/idempotency contract. Default local
composition still needs to inject the durable submitter and recovery loop
before this becomes a Public v1-qualified family. Public v1 remains
**0/13 (0%) — NO-GO**.
