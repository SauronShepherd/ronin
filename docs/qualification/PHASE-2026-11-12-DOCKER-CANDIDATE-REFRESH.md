# Phase 2026-11-12 — Docker candidate refresh

## Scope

Run the complete Docker qualification from a clean detached checkout, with the runner building the image itself from the candidate source. This covers real Docker execution, PostgreSQL-backed worker journeys, S3/Floci, Azure/Azurite, backup/restore, and strict v0.1 acceptance.

## Candidate binding

- Clean checkout: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-docker-clean-6a4a546`
- Source HEAD: `6a4a54678103cbe8a119251f7e011ac6a3527924`
- Runner: `tools/run_docker_qualification.ps1`
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-docker-qualification-6a4a546-rerun`
- Built image ID: `sha256:73787a1b2294f19e2d8ee2288e95fd780cac82456a55889787cef4f589bcafca`
- Qualification mode: `CLEAN-CANDIDATE QUALIFICATION`

## Iteration

The first candidate-bound attempt reached 23/27 tests but the local Docker Desktop Linux engine disappeared during the run, causing simultaneous service connection failures and cleanup errors. That run was rejected as non-qualifying infrastructure failure. Docker Desktop was restarted and the run was repeated with a new evidence directory; the second run completed with stable services and successful cleanup.

## Authoritative execution

```text
pwsh -NoProfile -File tools/run_docker_qualification.ps1 \
  -ImageTag ronin:qualification-6a4a546-rerun \
  -EvidenceDirectory C:\Users\angel.alvarez\AppData\Local\Temp\ronin-docker-qualification-6a4a546-rerun
```

Result: **PASS**.

- Docker integration: **27 passed, 0 skipped, 0 failed** in 266.58 s
- Strict v0.1 acceptance: **15/15 passed**, 0 skipped, 0 failed
- Providers exercised: PostgreSQL + Docker worker, Floci/S3, Azurite/Azure
- Cleanup: PASS; isolated services/resources removed successfully

## Qualification boundary

This closes the Docker candidate-refresh phase. It strengthens shared execution, packaging, persistence, and provider evidence but does not by itself qualify a complete Public v1 family. Public v1 remains **0/13 (0%) — NO-GO** pending complete family journeys and independent legal, human, provider, recovery, and release-governance gates.

