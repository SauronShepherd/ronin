# Qualification receipt — static Chromium web current

- Date: 2026-11-13
- Source checkout: `4aeb669dba1c179e63e40a36a8a84af2a9b78263`
- Runner: from `web-tests`, `npm test -- --workers=1 --reporter=line`; configured Playwright grep excludes `[Ll]ive` tests.
- Result: **180 passed, 0 failed** in 10.8 minutes.
- Scope: accessibility checks, responsive viewports, keyboard navigation, route traversal, connection/server settings, SQL/QueryFlux, catalog/lineage, scheduler, ML, semantic, streaming, synthetic and workspace/project journeys.
- Boundary: static Chromium evidence only; live UI/API, installed-package browser evidence, manual visual review and complete family/release qualification remain separate gates.
