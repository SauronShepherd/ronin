# Phase receipt — RPV1-802 notification intent conflict safety

## Status

**PASS** for the implemented notification identity slice on candidate
`8f255f603786779d80eb4403ce7a4dbaad7d1a25`.

## Change

- `SqliteTelemetryStore.put_notification_intent` now serializes the identity
  check and insert with `BEGIN IMMEDIATE`.
- Identical replay of an intent remains idempotent.
- Reusing an intent ID with different immutable content now raises the typed
  `NotificationIntentConflict` instead of silently discarding the new payload.
- The conflict type is exported through the observability package contract.
- Added regression coverage for same-ID/different-payload rejection.

## Evidence

- Notification/alert/FinOps focused suite: **29 passed, 0 failed**.
- Full Python regression (`python -m pytest --ignore=tests/perf -q`):
  **4585 passed, 80 skipped, 0 failed** in 335.08 s.
- Ruff check, Ruff format check and `git diff --check`: **passed**.

## Boundaries

This closes only the implemented RPV1-802 notification identity slice. It
does not claim exactly-once external delivery, SMTP/webhook certification,
or release qualification. Public v1 remains **0/13 active families, 0%,
NO-GO**, with `release_status=incomplete` and
`qualification_status=qualification_pending`.

Policy: qualification was manual and local; no GitHub Actions, branch or
worktree was used.
