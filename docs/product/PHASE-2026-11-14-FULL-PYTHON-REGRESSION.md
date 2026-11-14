# Full Python regression — current candidate

Date: 2026-11-14  
Baseline: `6d674f78822444b1d47011b466e3124c7495cf51`  
Policy: manual qualification only; GitHub Actions is intentionally absent.

## Gate executed

```text
python -m pytest --ignore=tests/perf -q
```

Result: **4577 passed, 80 skipped, 0 failed** in 423.67s (7:03).

The skips are explicit environment/provider/platform boundaries, including
Docker, PostgreSQL, S3/Azure/Trino/OTLP, POSIX symlink/mode behavior, external
SDP/Spark configuration and opt-in live worker acceptance. They are not counted
as passes and remain release gates where required by the plan.

The official ledger remains **0/13 (0%), NO-GO**.
