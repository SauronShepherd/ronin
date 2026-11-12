# Phase receipt — QueryFlux lifecycle serialization — 2026-11-12

## Candidate

- Source: `4ab4c8376319da4f6ff38ffa894357375252a393`
- Scope: SQLite and PostgreSQL QueryFlux execution stores

## Finding and correction

Both stores previously read the execution before opening the write
transaction. A concurrent success/cancel interleaving could therefore use a
stale state and lose cancellation intent or attempt an invalid transition.

The stores now read and validate the current row inside the write transaction:

- SQLite uses `BEGIN IMMEDIATE` before the read/update sequence.
- PostgreSQL uses `SELECT ... FOR UPDATE` before applying the transition.
- A stale cancellation request against a terminal row is idempotent and cannot
  reopen or invalidate the terminal state.

## Verification

```text
python -m pytest -q tests/test_queryflux_lifecycle.py \
  tests/test_data_engineering_plugin.py \
  tests/test_data_engineering_query_execution.py \
  tests/integration/test_data_engineering_http.py
39 passed
python -m compileall -q python/studio_data_engineering/queryflux_lifecycle.py
git diff --check
```

The lifecycle test now exercises two independent SQLite store instances
attempting success and cancellation concurrently and asserts a valid final
state without a lost cancellation flag.

## Boundary

PASS for the local lifecycle serialization subphase. This does not claim the
planned public asynchronous QueryFlux POST, worker replay/recovery, provider
handle persistence, or public cancel route; those remain open and are required
before the P3/P4 family can be release-qualified. Public v1 remains **0/13
(0%) — NO-GO**.
