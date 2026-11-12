# P4/P8 — Local PySpark qualification on current candidate

**Date:** 2026-11-12  
**Candidate SHA:** `31095606fb39730f36356cb4823f3b7a2becd8e9`  
**Runner:** `tools/local_spark_qualification.py` in a clean detached worktree  
**Evidence:** `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-spark-qualification-3109560.json`

## Result

The bounded local PySpark gate passed with explicit correctness evidence:

- provider: `pyspark-local`;
- Spark: `3.5.9`;
- runtime: Python `3.13.15`;
- output rows: `[('a', 2), ('b', 1)]`;
- correctness digest equals the expected digest:
  `0658e466e8922f1446a0cf87a9a2a2c43d106f93daee34f0396c06ee73707579`;
- timeout bound: 45 seconds, completed successfully.

The runner was hardened in the candidate to parse the final JSON object after
benign Spark/JVM diagnostics, and its regression suite passed **3/3**.

## Boundary

This is local PySpark evidence only. It does not certify a remote Spark Connect
or SDP provider, worker protocol conformance, or complete P4/P8/Public v1
family journeys. Those external-provider and family gates remain open.

