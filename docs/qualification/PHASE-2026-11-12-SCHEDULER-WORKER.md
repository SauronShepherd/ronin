# Phase receipt — scheduler and worker contracts — 2026-11-12

## Candidate

- Source candidate before this receipt: `33e37793b98dcd3ff75bb8740740b76290eca0c4`.

## Evidence

- The complete focused selection collected **200 tests** across all `tests/test_scheduler_*.py` modules plus notification and worker contract modules.
- It was executed in two terminal groups to remain within the observation limit:
  - first group: `117 passed in 25.81s`;
  - second group: `83 passed in 29.59s`.
- Aggregate: **200/200 passed**, 0 failures.

The selection covers scheduler adapters, cron, controller/daemon, leadership and fencing, cancellation/timeouts, backfill, branching, execution bridge/outbox, SQL/store behavior, notifications, worker execution/preparation/runtime, portable evidence, and in-flight cancellation.

## Scope boundary

These are local contract/regression tests. They do not claim the opt-in PostgreSQL multiworker/daemon-crash journey, provider operator conformance, or complete installed P5 family qualification.

## Result

PASS for the local scheduler/worker contract surface: **200/200**. P5 remains partial and Public V1 remains `0/13 (0%)` pending real recovery and operator/provider evidence.
