# Qualification receipt — OpenLineage transport and validation current

- Date: 2026-11-13
- Source checkout: `d654a6ff6f280dcc616b58be65d15a819bdbb330`
- Focused command: `python -m pytest -q tests/test_openlineage_transport.py tests/test_openlineage_export.py tests/test_openlineage_survivor_boundaries.py tests/test_transport_runtime_survivor_boundaries.py tests/test_ir_rql_openlineage_boundaries.py`.
- Result: **165 passed, 0 failed** in 1.99 seconds.
- Covered boundaries: event shape/schema and timezone validation, finite JSON and byte bounds, bounded retry/deduplication, redirect rejection, and transport error preservation.
- Boundary: this is transport/contract evidence only; external consumer round-trip, durable outbox delivery/reconciliation and provider certification remain open.
