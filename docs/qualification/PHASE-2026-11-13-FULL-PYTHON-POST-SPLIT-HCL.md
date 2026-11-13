# Qualification receipt — full Python regression after split HCL

- Date: 2026-11-13
- Source checkout: `42eaa917`
- Command: `python -m pytest -q --ignore=tests/perf`
- Result: **PASS — 4555 passed, 80 skipped, 0 failed** in 853.15 seconds.

This regression covers the split Terraform HCL generation and the existing
Cloud Studio/LocalStack qualification runner. Skips remain explicitly opt-in
or host-capability dependent and are not treated as PASS. External provider,
AWS Emulator, legal/manual, and Public v1 family gates remain separate.
Official status remains **0/13 (0%), NO-GO**.
