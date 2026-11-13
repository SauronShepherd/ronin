# Qualification receipt — full live product current diagnostic

- Date: 2026-11-13
- Source checkout: `feb53a05dbe727cb29bfdd4691b658ffca339299`
- Qualification mode: **DIRTY-WORKTREE DIAGNOSTIC**; preserved user artifacts and the user-owned public status edit were present.
- Worker image: `ronin:qualification` rebuilt from the current checkout, digest `sha256:0700bfea8db332caa52a59c335fec2f6f75753ca68e29c05590375327ecb2cd5`.
- Result: **33/33 Playwright cases passed, 0 skipped, 0 failures**.
- Coverage: 25 active routes, 24 API-backed and 1 UI-only; **282 real API events**, all correlated with structured HTTP logs (266 OK, 16 expected WARN); 0 server/network errors.
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-live-full-current-20261113083709`.
- Cleanup: PostgreSQL, streaming broker, volume and network cleanup succeeded.
- Boundary: current exact-HEAD diagnostic evidence, not clean-candidate release evidence; visual/manual review and complete Public v1 family qualification remain open.
