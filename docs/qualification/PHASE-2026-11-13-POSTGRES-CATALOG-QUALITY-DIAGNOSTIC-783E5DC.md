# Qualification receipt — PostgreSQL catalog and quality diagnostic

- Date: 2026-11-13
- Source checkout: `783e5dc614b5b1380500ae08c2a47c97c93cc71d`
- Qualification mode: **DIRTY-WORKTREE DIAGNOSTIC**; preserved user artifacts and the user-owned public status edit were present.
- Service profile: isolated PostgreSQL 16.4 Alpine.
- Selection: `-TestFilter 'catalog or quality'`.
- Result: **300 passed, 2 skipped, 0 failed** in 65.37 seconds.
- Skips: the two real Docker tests are opt-in and require the dedicated Docker qualification runner.
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-postgres-catalog-quality-20261113075318`.
- Cleanup: PostgreSQL service cleanup succeeded.
- Boundary: this is real PostgreSQL provider evidence for the selected catalog/quality slice, but it is not a clean-candidate gate and does not close the complete P6/P7 qualification or the full PostgreSQL suite.
