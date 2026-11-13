# Qualification receipt — OTLP Collector real service (clean candidate)

- Date: 2026-11-13
- Source checkout: `976c7e9704fc1df814dd2e082d26adb706c91d41`
- Qualification mode: **CLEAN-CANDIDATE QUALIFICATION**.
- Collector: `otel/opentelemetry-collector-contrib@sha256:45392d534c1edcc809c2d112394029246bc679d2ae5ea7081414a1fc74f2c621`.
- Result: **1/1 real-service test passed, 0 skipped, 0 failed**.
- Scope: traces, metrics and logs through the pinned OTLP/HTTP Collector on loopback.
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-clean-otlp-20261113093305`.
- Cleanup: isolated Collector container removed successfully.
- Boundary: this does not close the complete observability family or any Public v1 family; official progress remains 0/13.
