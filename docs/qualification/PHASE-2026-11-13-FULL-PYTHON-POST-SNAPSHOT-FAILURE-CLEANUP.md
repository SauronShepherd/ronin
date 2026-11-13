# Qualification receipt — full Python regression after snapshot failure cleanup

- Date: 2026-11-13
- Source checkout: `935565a9`
- Command: `python -m pytest -q --ignore=tests/perf`
- Result: **PASS — 4552 passed, 80 skipped, 0 failed** in 514.14 seconds.

The additional passing case covers cleanup of a temporary snapshot when
`fsync` fails. Skips remain explicitly opt-in or host-capability dependent
(Docker, PostgreSQL, S3/Azure/Trino/OTLP, external CLIs, symlinks and
POSIX-only behavior). This receipt does not qualify external providers or a
Public v1 family; status remains **0/13 (0%), NO-GO**.
