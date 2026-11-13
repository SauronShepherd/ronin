# Qualification receipt — local PySpark qualification (timeout fix)

- Date: 2026-11-13
- Source checkout: working candidate before this receipt; the runner change is committed together with this evidence.
- Finding: the prior 30-second default timed out on the supported Windows host while the same worker passed with a 60-second explicit bound.
- Fix: aligned `tools/local_spark_qualification.py` with the published 45-second qualification bound.
- Result: **PASS** — `pyspark-local`, Spark 3.5.9, Python 3.13.15, two rows `[('a', 2), ('b', 1)]`, matching digest `0658e466e8922f1446a0cf87a9a2a2c43d106f93daee34f0396c06ee73707579`.
- Regression: **3 passed, 0 failed** (`tests/test_local_spark_qualification.py`).
- Boundary: local PySpark evidence does not certify remote Spark Connect, SDP, or the complete P4/P8/Public v1 family journeys; official progress remains 0/13.
