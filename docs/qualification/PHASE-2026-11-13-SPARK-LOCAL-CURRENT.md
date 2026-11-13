# Local PySpark qualification — current candidate

**Date:** 2026-11-13  
**Candidate SHA:** `4290ee08b37be5db73389c894e5df96c9faf0e79`

## Gates

Runner:

```text
python tools/local_spark_qualification.py
```

Result: **passed** with provider `pyspark-local`, Spark `3.5.9`, Python
`3.13.15`, two output rows `[('a', 2), ('b', 1)]`, matching correctness digest
`0658e466e8922f1446a0cf87a9a2a2c43d106f93daee34f0396c06ee73707579` and the
45-second timeout bound.

Regression:

```text
python -m pytest -q tests/test_local_spark_qualification.py
```

Result: **3 passed, 0 failed**.

## Boundary

This is local PySpark evidence only. It does not certify remote Spark Connect
or SDP providers, worker protocol conformance or complete P4/P8/Public v1
family journeys. Public v1 remains **0/13 (0%) — NO-GO**.
