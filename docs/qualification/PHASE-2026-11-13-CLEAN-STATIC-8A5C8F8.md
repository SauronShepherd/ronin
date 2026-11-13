# Qualification receipt — clean-candidate static quality gates

- Date: 2026-11-13
- Source checkout: `8a5c8f8001c7eb07c75f20b1f84d139d53992472`
- Qualification mode: **CLEAN-CANDIDATE QUALIFICATION** in temporary checkout `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-clean-quality-20261113084724`.
- Static gates: Ruff format (941 files), Ruff lint, OpenAPI snapshot, architecture, negative gates, route consistency (199 operations), Studio surface, web audit, Studio budget, dependency surfaces and capability status — all passed.
- Focused tests: **67 passed, 1 skipped, 0 failed**; the skip is the Windows symlink-negative test.
- Web measurement: 71 assets, 37 JS modules, 15 stylesheets, 2,167,632 asset bytes, no web-audit failures.
- Ledger validation: generator check and all public-status/capability tests passed.
- Boundary: clean static qualification only; provider, live, Docker/Helm, manual visual/legal review and 13-family release qualification remain separate gates.
