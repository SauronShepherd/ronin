# Full regression after mypy/skill-manifest fix

Date: 2026-11-14  
Baseline: `7b78262409ee2c208e2bdb82585ac2362376b70f`  
Policy: manual qualification only; GitHub Actions is intentionally absent.

## Gate executed

```text
python -m pytest --ignore=tests/perf -q
```

Result: **4577 passed, 80 skipped, 0 failed** in 655.85s (10:55).

The skips remain explicit Docker/PostgreSQL/provider, external SDP/Spark,
Trino/OTLP, POSIX/symlink and opt-in live-worker boundaries. They are not
counted as passes.

The official ledger remains **0/13 (0%), NO-GO**.
