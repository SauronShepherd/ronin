# Verification sweep — `069023e`

**Observed main:** `069023ea65923ac16640d139088f0ea1fc1358b5`  
**Date:** 2026-09-06  
**Purpose:** preserve one exact-head view across architecture, security, QA, performance, product and community findings before Week 1 begins.

## Claims verified on this head

- Strict v0.1 acceptance is fail-closed by default. Development CI uses the explicit `--progress-only` mode; prerelease tag publication uses strict qualification.
- The frozen acceptance manifest contains exactly fifteen required `test_step_XX_*` names. A local reconstructed run of the current scaffold produced `live=0 passed=0 skipped=15 ... strict_success=false`; strict mode exited `1` and progress mode exited `0`.
- PR #98 is merged on this head. Post-merge `main` CI/release/security/docker workflows for this SHA completed successfully.
- Task cancellation persists `cell.cancelled` and `session.cancelled` before propagation.
- Pure-package low-level `os` access is rejected by the architecture gate.
- The development dependency graph is hash-locked and required CI installs it with `--require-hashes`.
- `docker/Dockerfile` is digest-pinned; the dedicated Docker qualification workflow still bootstraps from a mutable Python tag and is tracked separately.
- Pull-request secret qualification scans candidate history rather than only the final tree.

## Open findings revalidated by the 2026-09-06 sweep

| Finding | State on `069023e` |
|---|---|
| #55 repository URI query/fragment secrets | Open P1; `RepositoryBinding` rejects user-info credentials but still permits secret-bearing query/fragment components. |
| #60 Docker qualification image pin | Open P2; qualification pulls a mutable Python tag before deriving identity. |
| #45 security reporting policy | Open P1; no repository security-reporting policy exists. |
| #70 contributor onboarding surface | Open P1; contributor/conduct/templates surface is incomplete. |
| #58 transitive license qualification | Open P1; exact lock exists but exact license/NOTICE qualification does not. |
| #50 runtime capability/version selection | Decision required at sweep start; resolved by the 2026-09-06 decision pass. |
| #84 async event sink | Open P2; durable filesystem append remains synchronous in the async execution path. |
| #69 performance guards | Open P2; no committed bounded performance-budget suite. |
| #47 mutation depth | Open P1; mutation qualification remains core-only. |
| #63 repository protection | Decision required at sweep start; resolved by the 2026-09-06 decision pass. |

## Defects that must be visible to normal Builder ingestion

The sweep reconfirmed six previously under-signalled defects. Existing Week-1 issues are the canonical implementation surfaces where they already exist; they must carry structured automation handoffs rather than spawning duplicates.

- N3 — runner/container cleanup on ordinary exceptions: canonical Week-1 issue #76.
- N4 — fail-open default isolation qualification: canonical Week-1 issue #78.
- N8 — Docker memory limit does not cap swap and accepts ambiguous unitless values: canonical Week-1 issue #77.
- N2 — truncation can discard the useful output prefix: canonical Week-1 issue #76.
- B8 — runtime failure messages lose useful bounded/redacted context: canonical Week-1 issue #81.
- P1/P2 lookup hot paths — `Node.param` rebuilds a tuple before bisect and `OperatorCatalog.get` remains linear: canonical Week-1 issue #83.

## New structural findings

### Release-gating tools are outside measured coverage

`tools/` is inside the format/lint/type perimeter but absent from `[tool.coverage.run].source` and the T1/T2/T3 coverage reports. `tools/v01_acceptance_gate.py` now makes a release-critical decision, so this is a P1 infrastructure handoff. The fix is tracked separately rather than silently expanding a coverage tier in this verification commit.

### Optimization slices need end-to-end benefit evidence

The binary-search work already demonstrates the correct `bisect_left(..., key=...)` idiom in several catalogs while leaving the two measured hot paths unchanged. Builder review must therefore ask whether the expected benefit survives adjacent unchanged code and cite a measurement before accepting a performance claim.

## Exact-head qualification rule

Only check/workflow runs whose `head_sha` equals the exact candidate SHA qualify that candidate. Runs from superseded heads are informational and never block or satisfy merge qualification. This rule is formalized in `BUILDER_OPERATING_RULES.md`.
