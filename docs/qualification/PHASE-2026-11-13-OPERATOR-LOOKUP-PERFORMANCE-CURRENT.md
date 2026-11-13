# Qualification receipt — immutable operator lookup performance

- Date: 2026-11-13
- Change: precomputed immutable indexes for `Node.param()` and `OperatorCatalog.get()`.
- Full gate: `python -m pytest -q` — **4563 passed, 80 skipped, 0 failed** in 781.49 seconds.
- Focused budgets: `tests/perf/test_budgets.py` — **3 passed**.
- Operator regression coverage: **48 passed**.
- Cloud Studio web audit: **ok=true, controls=14, features=11**.
- Cloud Studio browser E2E: **passed**.
- Boundary: this closes local accessibility/performance evidence only; provider and Public v1 family qualification remain separate gates.
