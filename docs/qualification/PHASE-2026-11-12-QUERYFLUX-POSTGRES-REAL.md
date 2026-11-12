# Phase receipt — real PostgreSQL QueryFlux lifecycle — 2026-11-12

## Candidate and environment

- Source: `b326bc07b61af0d11e9db5afdc7ec80a7971f331`
- PostgreSQL: `postgres:16.4-alpine`
- DSN: isolated loopback container, synthetic credentials only
- Cleanup: container removed after the run

## Executed gate

The real PostgreSQL store was exercised through the following lifecycle:

1. create an execution and repeat creation with the same identity;
2. transition `queued → running`;
3. request cancellation and verify `running → cancelling` with the durable flag;
4. repeat cancellation idempotently;
5. transition to `cancelled` and verify terminal immutability;
6. issue a stale cancellation against the terminal identity and verify no
   mutation.

The isolated runner output was:

```text
POSTGRES_QUERYFLUX_LIFECYCLE_PASS
```

## Decision

PASS for real PostgreSQL persistence and lifecycle semantics on the tested
candidate. This does not qualify the asynchronous public QueryFlux worker,
provider handle persistence, restart recovery, Trino/provider conformance, or
public cancel routes. Public v1 remains **0/13 (0%) — NO-GO**.
