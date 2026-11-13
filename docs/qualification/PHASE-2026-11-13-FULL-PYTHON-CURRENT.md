# Qualification receipt — full Python regression suite

- Date: 2026-11-13
- Source checkout: current `main` candidate at execution time.
- Command: `python -m pytest -q`.
- Result: **4550 passed, 80 skipped, 0 failed** in 976.33 seconds.
- Skips: documented opt-in Docker/PostgreSQL/provider/SDP/OTLP/Trino cases plus Windows POSIX/symlink capability cases; no skip was promoted to pass.
- Decision: full local Python regression gate **PASS**, with environment-scoped evidence boundaries preserved.
- Boundary: this suite does not replace real provider journeys, legal review, human release approval, or complete Public v1 family qualification; official progress remains 0/13.
