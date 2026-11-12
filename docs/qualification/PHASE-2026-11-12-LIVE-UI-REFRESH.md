# Phase 2026-11-12 — Live product UI refresh

## Candidate

- Source commit: `33fc67af13ff8ff86ecd4e14d27e8d1de012cb53`
- Worker image: `ronin:qualification-33fc67a`
- Worker image ID: `sha256:960ef229b3adfad4fe0c6c24dc5043b85e2f3fd7507014fdc546ca82cb802cf4`
- Qualification mode: clean-candidate

## Fix exercised

The connection submit capture handler now persists the entered token into both the in-memory API config and `sessionStorage` before route refresh. Runs therefore cannot render the unauthenticated empty state during the connection-to-route transition.

## Gates

- Playwright live cases: **33/33 passed**, 0 skipped, 0 failed.
- Active routes audited: **25**.
- API-backed routes: **24**; UI-only routes: 1.
- Real services: PostgreSQL, Kafka and Ronin API all ready.
- API events: **283**, all 283 correlated with structured HTTP logs.
- Outcomes: 267 OK, 16 expected WARN, 0 uncorrelated.
- Application logs: 0 ERROR, 0 CRITICAL.

## Prior failure and regression closure

The preceding candidate recorded 32/33 and failed `live Runs saves server settings and retains the project filter`; the UI remained on “Connect a server” after saving the token. This candidate passes that case and the full suite.

## Decision

Live product phase: **PASS**.

Public v1 remains **0/13 (0%) — NO-GO** until the complete Public v1 evidence family is closed. The Trivy residual remains explicit and open: one `UNKNOWN` Go stdlib finding pending upstream `1.27.4`; no critical/high/medium/low findings were reported.
