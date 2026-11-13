# Qualification diagnostic — full Python gate after Terraform validation changes

- Date: 2026-11-13
- Source before diagnostic: `a6453872`.
- Command: `python -m pytest -q`.
- Result: **4557 passed, 80 skipped, 5 failed** in 2523.25 seconds.
- Failures: HTTP contention p95 budget; node parameter micro-budget; operator catalog micro-budget; two SQLite/worker lease contention scenarios reporting `attempt lease ownership lost`.
- Focused Cloud Studio result on the same change: **42 passed**, Ruff clean.
- Interpretation: no Cloud Studio regression was identified by the focused suite. The full gate remains non-green and no phase or Public v1 family is qualified by this receipt.
