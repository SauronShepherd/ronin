# Qualification receipt — scheduler and backfill contracts current

- Date: 2026-11-13
- Source checkout: `c05879563c97cc26a5657876b33f84306c5e2765`
- Selection: all Python tests whose paths cover scheduler/backfill/stream scheduler bridges (`24` test modules).
- Result: **146 passed, 0 failed** in 25.55 seconds.
- Scope: cron/timezone preview, branch state, durable backfill store/runtime/HTTP/cancellation, scheduler adapters/daemon/controller/leadership/fencing, execution outbox, pools, notifications, SQL, timeouts and stream bridge contracts.
- Boundary: local contract/regression evidence only; PostgreSQL multiworker crash/replay, external notification/provider conformance, and complete P5 family qualification remain open.
