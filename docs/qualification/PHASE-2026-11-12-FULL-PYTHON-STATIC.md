# Phase receipt — full Python and static gates

- Date: 2026-11-12 (Europe/Madrid)
- Candidate SHA tested: `160ce5434e41d8932f93f64ff11db61bb039f08c`
- Scope: full local Python suite and the non-service gates represented by `make check`.
- This receipt does not qualify external providers, Docker/Helm, browser live journeys, or the release candidate.

## Executed checks

| Check | Result |
| --- | --- |
| Full Python suite with coverage collection | PASS — 4525 passed, 77 skipped, 0 failed, 466.42s |
| Ruff format | PASS — 918 files already formatted |
| Ruff lint | PASS |
| OpenAPI snapshot | PASS — digest `fe364bd58ac3044064cf4d2653c26e79b34586a5e3f25b75c7db02aa4059e2da` |
| Mypy | PASS — 443 source files |
| Architecture and negative gates | PASS |
| Route consistency | PASS — 197 operations |
| Studio surface | PASS — 128/239 published operations matched |
| Web audit | PASS — 72 files, 0 failures |
| Web budget | PASS |
| Dependency surfaces | PASS |
| Capability status | PASS |
| Agent skills validation | PASS — 3 skills valid |

## Explicit skips

The 77 skips are environment-scoped and include real Docker, PostgreSQL, S3/Azurite, Trino, OTLP and Spark services, Windows symlink privileges, and provider credentials. They are not converted into PASS and remain open qualification work.

## Progress accounting

- Release-qualified families: `0/13 = 0%`.
- Release status: `NO-GO` / `qualification_pending`.
- No RPV1 item is closed by this receipt; local gates establish evidence for this candidate only.
