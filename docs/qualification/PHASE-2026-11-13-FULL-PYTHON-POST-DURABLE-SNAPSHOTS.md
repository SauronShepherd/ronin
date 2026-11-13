# Qualification receipt — full Python regression after durable snapshots

- Date: 2026-11-13
- Source checkout: `99b8c168`
- Command: `python -m pytest -q --ignore=tests/perf`
- Result: **PASS** — **4551 passed, 80 skipped, 0 failed** in 548.62 seconds.

The skipped cases are explicitly opt-in or host-capability dependent: Docker,
PostgreSQL, S3/Azure/Trino/OTLP endpoints, external SDP/Spark CLI, symlinks,
POSIX-only behavior, and artifact-link privileges. They do not represent
failed assertions and remain separate from provider qualification.

Boundary: this receipt covers the Python regression suite only. It does not
qualify external providers, AWS Emulator, manual/legal/release gates, or any
Public v1 family. Official status remains **0/13 (0%), NO-GO**.
