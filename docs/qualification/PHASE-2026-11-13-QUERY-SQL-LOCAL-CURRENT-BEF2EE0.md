# Qualification receipt — SQL local and QueryFlux contracts current

- Date: 2026-11-13
- Source checkout: `bef2ee091d664e1c7f17cc7707cd4e9a71a27192`
- Harness: `python -m tools.query_engine_qualification` returned local provider `ronin-local-sql` as `qualified`, query state `succeeded`, 2 rows, matching correctness/expected digest `2032c0cffe00f42b6cf39f776b036907ab6ed106530b415ca6965a64a3afcdc7`; bounded preview qualified and unauthorized/invalid profiles rejected.
- Focused command: `python -m pytest -q tests/test_query_engine_qualification.py tests/test_query_engine_contracts.py tests/test_query_engine_local.py tests/test_queryflux_lifecycle.py tests/test_queryflux_result_paging.py tests/test_sql_http.py tests/test_sql_wire.py`.
- Result: **89 passed, 0 failed** in 4.20 seconds.
- Boundary: external QueryFlux remains `not_configured`; cancellation, timeout, queue capacity and provider restart remain unsupported/unconfigured. Trino/OTLP evidence is separate; P3 remains partial.
