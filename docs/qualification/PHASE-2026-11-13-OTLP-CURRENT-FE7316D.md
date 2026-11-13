# Qualification receipt — OTLP Collector real service current

- Date: 2026-11-13
- Source checkout: `fe7316df713523dd43b353b5253666a380558446`
- Runner: `tools/run_otlp_qualification.ps1 -AllowDirtyWorktree`.
- Collector: `otel/opentelemetry-collector-contrib@sha256:45392d534c1edcc809c2d112394029246bc679d2ae5ea7081414a1fc74f2c621`.
- Result: **1/1 real-service test passed, 0 skipped, 0 failed**.
- Scope: traces, metrics and logs ingestion through the pinned OTLP/HTTP Collector on loopback.
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-otlp-current-fe7316d-20261113064741\qualification.json`.
- Cleanup: isolated Collector container removed by the runner.
- Boundary: broader P12 service adoption, alert delivery, cost/budget behavior, complete product journeys and clean release aggregation remain open.
