# Qualification receipt — live product current

- Date: 2026-11-13
- Source checkout: `299658236c07f8e3e266c524e44df48b734ae3ac`
- Worker image: `ronin:qualification-live-7e4e3fe` (`sha256:75e4de20d775c376aaf42367978f514a193e8c74c4616f6bed95ea6f641026d6`)
- Runner: `tools/run_live_product_qualification.ps1 -WorkerImage ronin:qualification-live-7e4e3fe`
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-live-current-final-20261113073715`
- Result: **33/33 passed, 0 skipped, 0 failed**; 25 active routes audited, 24 API-backed and 1 UI-only.
- Traffic: **280** real API events, all correlated with structured server logs; 264 OK, 16 expected WARN, 0 uncorrelated, 0 server/network errors and 0 application ERROR/CRITICAL.
- Correction: live helpers now wait for the rendered Studio navigation before opening Server connection, eliminating the pre-listener interaction race.
- Cleanup: isolated PostgreSQL/streaming services and evidence collection completed successfully.
- Boundary: this closes the live product qualification gate for this candidate; Public v1 remains conservatively unqualified at 0/13 families until all family and release/provider gates close.
