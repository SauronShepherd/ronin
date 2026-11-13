# Qualification receipt — full Python regression current

- Date: 2026-11-13
- Source checkout: `3341f9758fdf72c689435ceb4ff72df5d0748e3b`
- Command: `python -m pytest -q --junitxml <evidence>\\pytest.xml`.
- Result: **4547 passed, 80 skipped, 0 failed** in 722.26 seconds.
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-full-python-current-3341f97-20261113060710\pytest.xml`.
- Skip boundary: opt-in Docker/PostgreSQL/S3/Azure/Trino/OTLP/Spark integrations, external credentials, and Windows symlink/POSIX-specific checks remain intentionally outside this host-only regression and are covered by their dedicated receipts where available.
- Qualification boundary: this closes the current host regression gate; it does not by itself qualify any complete Public v1 family or release candidate.
