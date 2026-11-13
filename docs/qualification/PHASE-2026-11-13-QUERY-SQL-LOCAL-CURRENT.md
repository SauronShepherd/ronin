# Local SQL and QueryFlux contract qualification — current candidate

**Date:** 2026-11-13  
**Candidate SHA:** `f86823ce1955e3bbb8d553ce8f9a9f5085a11cb1`

## Gates

The local query harness:

```text
python -m tools.query_engine_qualification
```

returned `ronin-local-sql` status `qualified`, with state `succeeded`, two
rows, matching correctness digest
`2032c0cffe00f42b6cf39f776b036907ab6ed106530b415ca6965a64a3afcdc7`, bounded
preview qualified and unauthorized/invalid profiles rejected.

Focused SQL/QueryFlux regression:

```text
python -m pytest -q tests/test_query_engine_qualification.py tests/test_query_engine_contracts.py tests/test_query_engine_local.py tests/test_queryflux_lifecycle.py tests/test_queryflux_result_paging.py tests/test_sql_http.py tests/test_sql_wire.py
```

Result: **89 passed, 0 failed** in 9.29 seconds.

## Boundary

The harness reports external QueryFlux as `not_configured`; cancellation,
timeout, queue-capacity and provider-restart rows remain unsupported or
unconfigured. Trino evidence is recorded separately. P3 remains partial and
Public v1 remains **0/13 (0%) — NO-GO**.
