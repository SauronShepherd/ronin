# Qualification receipt — streaming-only Redpanda diagnostic

- Date: 2026-11-12
- Source checkout: `20d3d9a6b63e4f0756ed5d4d5b2260ebdaa682ae`
- Runner: `tools/run_live_product_qualification.ps1 -TestGrep streaming`.
- Runtime: isolated Kafka-compatible Redpanda service, with PostgreSQL intentionally omitted by the streaming-only profile.
- Result: **1/1 Playwright passed, 0 skipped, 0 failed**; 38 real API events fully correlated; 0 unexpected authorization gaps and 0 server/network errors.
- Cleanup: isolated Redpanda container and network removed successfully.
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-live-evidence-streaming-only-20d3d9a`.
- Boundary: this qualifies the current streaming route against Redpanda; broader P11 operational evidence, persistence/recovery matrices, provider breadth and full-family qualification remain open.
