# Autonomous build backlog

This backlog is deliberately narrow for v0.1. Selection must be revalidated against current `main`, open Builder work, canonical automation handoffs, and the scope authority in `docs/product/V01_SCOPE.md`.

_Last synchronized: 2026-09-10 after #162 secure bearer-transport implementation under code-only validation mode._

**Planning synchronization rule.** `BACKLOG.md` and `CONSTRUCTION_PLAN.md` must be updated together from the same observed repository state whenever acceptance truth, completed capabilities, validation mode, or the critical path changes materially. If the two files disagree, autonomous product selection stops until the drift is reconciled.

## Current validation mode

GitHub Actions are intentionally disabled to avoid consuming Actions credits. Previous workflow definitions are retained under `.github/workflows-disabled/` only as historical/restart material.

Until the maintainer explicitly changes this policy, autonomous Builder work does not wait for, trigger, rerun, or require CI; does not execute automated tests; validates through static code inspection, dependency/contract tracing, schema/API consistency review, and code-level reasoning; and does not claim green CI or passing tests for new changes. Existing security, durability, performance, architecture, coverage, and acceptance requirements remain implementation constraints.

Evidence-only handoffs #166/#167/#163 remain open/deferred and do not block implementation while this mode is active.

## Current v0.1 truth

The last automated qualification before CI was disabled remains **13/15 live**, with exact historical gaps `01` (production image + supported Compose topology) and `12` (public portable evidence retrieval). Code-only work does not alter that qualified baseline automatically.

Supported code now contains the durable local execution spine, authenticated and project-scoped HTTP job control, OpenAPI 3.1, `pyronin`, operator CLI, typed scoped grants (#52), public portable evidence (#53), strict-alpha API/SDK compatibility (#54), route-level typed grant enforcement (#161), production image + Compose (#180), and secure-default bearer transport (#162).

B1 / #48 is complete. #52, #53, #54, #161, and #162 are functionally complete in code-only mode. Step 01 and step 12 capabilities are functionally present but **not yet re-qualified** under the disabled-test policy. PR #159 remains closed without merge and is only historical reuse evidence.

#57 remains open/BLOCKED as a qualification gate. The acceptance harness still carries stale step-01/step-12 skip markers, and no 15/15 claim is permitted until automated qualification is explicitly restored and executed.

## Production image + Compose implementation

The supported local container path provides one digest-pinned Ronin image, durable `/var/lib/ronin` storage, server health gating, host loopback publication, worker-only Docker socket authority, immutable local image-ID resolution, read-only checkout access, narrowly scoped Git safe-directory handling, non-root product execution, worker `restart: "no"`, and a bundled CLI helper.

The server and bundled CLI now explicitly opt into plaintext only for the private Compose bridge with `RONIN_INSECURE_ALLOW_REMOTE_HTTP=1`; the host-facing port remains bound to `127.0.0.1`.

No automated Compose/runtime qualification was executed under current maintainer policy.

## Secure bearer transport

Authenticated client transport now requires HTTPS for non-loopback endpoints by default. HTTP remains supported for explicit loopback (`127.0.0.1`, `::1`, `localhost`). The CLI rejects redirects so a bearer-bearing request cannot be silently redirected from a validated origin.

The supported `ronin serve` path is plaintext HTTP only and fails closed before a non-loopback bind unless `RONIN_INSECURE_ALLOW_REMOTE_HTTP=1` is explicitly set. This override is a local-development acknowledgement, not encryption. Remote supported use terminates HTTPS externally and keeps the Ronin backend on loopback or a trusted private network.

## Current critical path

Select one coherent slice at a time.

1. **#123 — untracked executable-bit Git identity.** Include executable-mode identity for untracked files without weakening fail-closed VCS capture.
2. **Release blockers/publication preparation.** Address actionable code/documentation portions of #58/#95/#73 and related release work under code-only policy; keep #63 blocked on repository administration/release timing and #45 blocked on the maintainer's private-reporting-channel decision.
3. **#57 qualification gate.** Do not select for implementation while tests/CI are disabled. Revisit only when the maintainer explicitly restores automated verification.

## D1 operator status

D1 is functionally complete in code: `serve`, `worker`, `submit`, `status`, `logs`, `jobs`, `cancel`, and installed `ronin evidence` are present. Automated qualification remains paused.

## Worker execution invariants

Every remaining worker/runtime slice must preserve checkpoint-before-next-cell persistence, lease fencing, fail-closed heartbeat ownership, prompt cancellation, immutable resume identity plus verified artifact availability/digest, same-Run replacement Attempts, exact reused-cell and `attempt_id` provenance, bounded async store/artifact facades, and production lease TTL semantics.

## Public-boundary and architecture invariants

Canonical contracts remain capability-driven and vendor-neutral. Do not introduce worker -> server dependency inversion. Physical evidence/storage locators are not canonical public identity. Static bearer auth remains the v0.1 mechanism; typed least-privilege scopes are required. Public `/v1` compatibility follows `docs/product/API_COMPATIBILITY_V1.md`. No OIDC, enterprise RBAC, OPA, FastAPI, Pydantic, SQLAlchemy, Postgres, Kubernetes product deployment, brokers, OpenTelemetry, or OpenLineage unless scope is explicitly revised.

For transport, built-in server TLS remains out of scope. Supported remote authenticated access is HTTPS at the client-facing boundary through an external TLS terminator/reverse proxy; loopback HTTP remains the normal local-development path. Plaintext non-loopback use requires the explicit insecure-development override and must remain confined to a trusted private network.

## Quality and release invariants

These remain implementation constraints while automated enforcement is paused: POST p95 <100 ms; GET p95 <30 ms; SQLite WAL + `synchronous=FULL`; fencing and fail-closed VCS capture; T1 100%, T2 90%, T3 75%, every `studio_storage` file >=80% once coverage execution is restored; and exact installed-artifact plus immutable Docker-digest qualification before release.

## Frozen until v0.1 ships

Ingestion/CDC breadth, SQL/lakehouse breadth, streaming, catalog/semantic BI, MLOps, GenAI/RAG, agents, Postgres/multi-node/HA, Kubernetes product scale, enterprise authorization and broad vendor integrations remain out of scope until the v0.1 freeze is explicitly lifted.

## Operational invariant

While code-only validation mode is active, implementation may merge after static review of the complete diff against current `main`. Do not run or wait for GitHub Actions/tests, and do not claim runtime/qualification evidence that was not actually produced.
