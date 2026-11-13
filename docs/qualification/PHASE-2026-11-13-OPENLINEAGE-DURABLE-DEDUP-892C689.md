# Qualification receipt — durable OpenLineage publication deduplication

- Date: 2026-11-13
- Source checkout: `892c689190970c1af6714c4fa7252de466e08316`
- Implementation: added optional bounded `SqliteOpenLineageDedupStore`; publication digests are marked only after a successful sink response and survive transport reconstruction/restart. The default in-memory behavior remains unchanged when no store is injected.
- Focused command: `python -m pytest -q tests/test_openlineage_transport.py tests/test_openlineage_export.py tests/test_openlineage_survivor_boundaries.py tests/test_transport_runtime_survivor_boundaries.py tests/test_ir_rql_openlineage_boundaries.py`.
- Result: **167 passed, 0 failed** in 2.39 seconds, including restart and failed-before-mark regression tests.
- Boundary: this provides a durable deduplication primitive; wiring it into an operational outbox/consumer delivery loop and external round-trip certification remain separate gates.
