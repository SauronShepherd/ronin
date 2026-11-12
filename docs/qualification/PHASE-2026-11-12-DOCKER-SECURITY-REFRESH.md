# Phase 2026-11-12 — Docker security and integration refresh

## Candidate

- Source commit: `a3da0015e00e11784a7969c9534f864bc3597ed4`
- Image tag: `ronin:qualification-a3da001`
- Image ID: `sha256:af97929e2fa30b60bf264696fac00e5c1497e7537618d1bc5116a8becec33b5d`
- Runtime base: Python 3.11 Alpine 3.24, pinned by digest
- Embedded Docker CLI: `29.10.0-rc.1-cli-alpine3.24`, pinned by digest

## Changes

- Added explicit `libcrypto3=3.5.9-r1` and `libssl3=3.5.9-r1` to the hash/version-locked Alpine runtime set.
- Updated the probe and runtime Docker CLI pin to the newer candidate release, addressing the Go stdlib finding present in 29.9.x.
- Updated the Docker qualification contract to cover the expanded locked package set.

## Gates

- Contract tests: **98 passed**.
- Real Docker qualification: **27 passed, 0 failed, 0 skipped**.
- Strict v0.1 acceptance: **15/15 passed**.
- Fixtures: PostgreSQL, Docker worker/runtime, Floci/S3, Azurite/Azure Blob, backup/restore and v0.1 journey.
- Trivy 0.76.1: **0 critical/high/medium/low findings; 1 `UNKNOWN` finding** (`CVE-2026-97054`, Go stdlib `v1.27.3`, fixed in `1.27.4`). This is retained as an explicit upstream residual and is not suppressed.

## Decision

Docker integration and strict acceptance are **PASS**. The security sub-gate is **PASS WITH OPEN UPSTREAM UNKNOWN**, not a claim of zero Trivy findings. The Docker phase is closed for the tested candidate; the remaining unknown must be rechecked when Docker publishes a CLI containing Go `1.27.4` or later.

Public v1 remains **0/13 (0%) — NO-GO** because this phase alone does not satisfy the complete Public v1 family evidence contract.
