# Qualification receipt — streaming-only Redpanda current

- Date: 2026-11-13
- Source checkout: `9aad8fa39ba460b6b1c040a4ca495717c781905d`
- Worker image: `sha256:60943a988b50ef7ed99f9b26b8736c71b5e523a9efc26b8b7bc93ec71daa37b6`
- Runner: `tools/run_live_product_qualification.ps1 -TestGrep streaming -AllowDirtyWorktree`.
- Runtime: isolated Kafka-compatible Redpanda service with the streaming-only profile.
- Result: **1/1 Playwright passed, 0 skipped, 0 failed**; live API traffic was captured and correlated, including accepted and deliberately rejected stream-input cases.
- Cleanup: isolated runtime resources were removed successfully by the runner.
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-live-streaming-9aad8fa-20261113055559`.
- Boundary: this closes the current streaming-only Redpanda lane; broader P11 operational evidence, persistence/recovery matrices, provider breadth, license decisions and full-family qualification remain open.
