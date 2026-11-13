# Qualification receipt — performance gate after durable snapshots

- Date: 2026-11-13
- Source checkout: `aad5de2b`
- Command: `python -m pytest tests/perf -q`
- Result: **PASS — 5 passed in 7.13 seconds**.

This is the repository performance test lane and confirms no regression in the
current bounded local contracts. It is not a production load/soak result and
does not cover external providers, Kubernetes, AWS Emulator, or Public v1
family qualification. Official status remains **0/13 (0%), NO-GO**.
