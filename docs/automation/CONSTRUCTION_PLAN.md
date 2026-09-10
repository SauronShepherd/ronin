# Ronin v0.1 construction plan

_Last synchronized: 2026-09-10 after #123 untracked executable-mode identity implementation under code-only validation. Scope authority: `docs/product/V01_SCOPE.md`. Target release: 2026-11-01._

Ronin remains capability-ordered rather than calendar-ordered. Each autonomous run selects at most one coherent implementation slice and revalidates against current `main`, open Builder work, canonical handoffs, and frozen v0.1 scope.

**Planning synchronization rule.** `BACKLOG.md` and `CONSTRUCTION_PLAN.md` are one canonical planning pair. Whenever acceptance truth, completed capabilities, validation mode, or the critical path changes materially, both files must be updated from the same observed repository state.

## Current validation mode

GitHub Actions and automated tests are intentionally disabled by maintainer policy. Previous workflow definitions remain under `.github/workflows-disabled/`. Autonomous work performs static code inspection, dependency/contract tracing, schema/API consistency review, and code-level reasoning only. Security, durability, performance, architecture, coverage, and acceptance requirements remain implementation constraints, but no new CI/test/acceptance evidence may be claimed.

The last automated baseline remains **13/15**, with historical gaps `01` and `12`. Code-only implementation does not automatically change that qualified result.

## Current position

The MVP durable local execution spine is implemented: Job -> Run -> Attempt lifecycle, SQLite/in-memory storage, bounded async composition, immutable resume identity, Docker worker execution/recovery, fencing/cancellation, authenticated HTTP job control, OpenAPI, `pyronin`, operator CLI, typed scoped grants, public portable evidence, strict-alpha public compatibility, project-scoped HTTP authorization, production image/Compose, secure-default bearer transport, and corrected untracked executable-mode Git dirty identity.

#52, #53, #54, #161, #162, and #123 are functionally complete under code-only validation. Automated drift/conformance, authorization, transport, VCS-regression and Compose qualification remain deferred, so the authoritative acceptance baseline remains 13/15.

#57 remains the frozen-journey umbrella and qualification gate: product code for all historical missing surfaces is present, but strict automated qualification has not proven the full journey on an exact SHA.

## Phase A — foundation

**Complete.** Deterministic domain/runtime/notebook/kernel contracts and architecture boundaries are present.

## Phase B — durable worker execution and resume

**Complete for the MVP spine.** Replacement Attempts remain in the same logical Run and preserve exact cell-reuse plus `attempt_id` provenance.

## Phase C — HTTP/API/SDK contract

**Status: functionally complete in code; automated qualification deferred.**

Completed:

- #52 provider-neutral typed scoped grants, bearer-scope mapping and kernel pre-effect authorization decisions;
- #53 durable/public portable evidence with `available`, `missing`, `tombstoned`, `unavailable`, locator privacy, authenticated HTTP, OpenAPI, CLI and `pyronin` surfaces;
- #54 strict-alpha API/SDK compatibility: closed response objects and semantic enums, open error-code vocabulary inside a normalized closed envelope, opaque bounded cursors, canonical Instant validation, and documented alpha/beta/stable evolution rules;
- #161 project-scoped HTTP authorization using the #52 grant model, including list filtering, direct Job-ID visibility checks, evidence authorization, pre-effect submit/cancel checks, and removal of the token-only server-constructor bypass;
- #162 secure-default bearer transport: CLI HTTPS-by-default for authenticated non-loopback endpoints, loopback HTTP support, redirect rejection, fail-closed plaintext non-loopback server binding, explicit local-development override, Compose-preserving private-bridge opt-in, and documented external TLS termination.

HTTP/server types remain adapters, never canonical lifecycle/storage models. No worker -> server dependency inversion is allowed. The built-in server remains plaintext HTTP only and does not claim TLS support.

## Phase D — operator CLI and Git identity

**Functionally complete in code under current policy.** D1 includes installed `ronin evidence` and secure-default authenticated transport. #123 now corrects `ronin/git-dirty-v1` so untracked regular-file identity includes normalized Git-style executable mode in addition to path, byte length and SHA-256(content).

On POSIX, the owner executable bit (`S_IXUSR`) maps to `100755`; otherwise the regular file maps to `100644`, matching Git's regular-file mode distinction. On non-POSIX platforms, untracked regular files normalize to `100644` rather than inferring executable semantics from extensions or platform-specific associations. Tracked mode changes remain represented by Git's own binary diff.

VCS capture remains fail closed for unresolved/path-escaping inputs, symlinks, special files and unreadable untracked files. Deterministic ordering and raw-content privacy are preserved. Automated real-Git regression proof remains deferred while tests are disabled.

## Phase E — production image, Compose and zero-to-demo

**Functionally complete in code; automated qualification deferred.**

The repository contains one production Ronin image and supported `compose.yaml` topology with durable local SQLite/artifact/evidence storage, explicit server health dependency, host loopback publication, worker-only Docker socket authority, immutable local image-ID resolution, read-only checkout access, narrowly scoped Git safe-directory configuration, non-root product execution, crash-path worker `restart: "no"`, and a no-Docker-authority CLI helper.

Because server and CLI communicate over the private Compose bridge, those two services explicitly set `RONIN_INSECURE_ALLOW_REMOTE_HTTP=1`. This does not broaden host exposure: the published server port remains loopback-only. Remote supported access requires HTTPS termination outside the built-in Ronin server.

The <60 s healthy and <10 min zero-to-demo budgets remain implementation targets, not newly measured evidence while tests/CI are disabled.

## Phase F — acceptance completion

**Last automated baseline: 13/15.** Historical gaps remain `01` and `12` until qualification is restored.

Code contains both step-01 Compose and step-12 public evidence capabilities plus the #54 compatibility, #161 scoped-authorization, #162 secure-transport, and #123 Git-identity corrections. `tests/e2e/test_v01_journey.py` still carries stale historical skip markers for 01/12; under maintainer policy those tests are not being edited or executed in code-only slices. Do not call the project qualified 14/15 or 15/15 while automated qualification is disabled.

#57 is therefore a blocked qualification gate, not an implementation slice.

## Phase G — security, non-functional and release work

The next bounded implementation slice is **#58 exact transitive license/NOTICE policy**. Add a regenerable direct+transitive dependency/license inventory tied to the resolved dependency graph, plus a fail-closed maintainer-review policy for unknown/unreviewed/potentially incompatible license changes. Do not bundle dependency upgrades or add ASF-style NOTICE boilerplate without evidence.

After #58, prioritize **#95 installed `pyronin` artifact qualification logic** where code-only work can prepare exact-artifact/outside-checkout mechanics without claiming runtime proof. Then address **#73 human-operable release/change communication**. #63 remains blocked on repository administration/release timing; #45 remains blocked on the maintainer selecting and verifying a private reporting channel. Test/CI-centric #47/#60/#102/#163/#166/#167 remain deferred while CI/tests are disabled.

Existing implementation constraints remain: POST p95 <100 ms; GET p95 <30 ms; SQLite WAL + `synchronous=FULL`; fencing; fail-closed VCS capture; T1 100%, T2 90%, T3 75%, every `studio_storage` file >=80% when coverage execution is restored.

## Phase H — release candidate and v0.1.0

**Not started.** Feature implementation alone is not release qualification. Automated acceptance, exact installed-artifact checks, immutable image identity, security/license/process blockers, version synchronization and ref protection must be satisfied before publication.

## Current critical path

One coherent Builder slice at a time:

1. **#58 exact transitive license/NOTICE policy** — resolved-graph inventory, fail-closed review policy and evidence-based NOTICE decision without dependency upgrades.
2. **#95 installed `pyronin` artifact qualification logic** — prepare exact candidate/outside-checkout qualification mechanics; defer runtime test evidence under current policy.
3. **#73 human-operable release/change communication** — truthful release runbook and user-facing alpha change communication coordinated with release blockers.
4. **#57 frozen-journey qualification** — revisit only after the maintainer explicitly restores automated tests/qualification; then remove stale acceptance skips and obtain strict exact-SHA 15/15 evidence without weakening the frozen contract.

## Architecture and scope guardrails

Canonical contracts stay capability-driven and vendor-neutral. Static bearer auth remains the v0.1 mechanism; typed scopes are required, enterprise auth is not. Evidence identity is storage-neutral and public payloads exclude backend locators. Public `/v1` compatibility follows `docs/product/API_COMPATIBILITY_V1.md`. Do not add OIDC, enterprise RBAC, OPA, FastAPI, Pydantic, SQLAlchemy, Postgres, Kubernetes product deployment, brokers, OpenTelemetry or OpenLineage unless scope explicitly changes.

Authenticated non-loopback clients require HTTPS by default. The built-in HTTP server remains plaintext and may bind non-loopback only with the explicit insecure-development override. Supported remote use terminates TLS externally and keeps Ronin's backend listener on loopback or a trusted private network.

## Frozen until v0.1 ships

Ingestion/CDC breadth, SQL/lakehouse breadth, streaming, catalog/semantic BI, MLOps, GenAI/RAG, agents, Postgres/multi-node/HA, Kubernetes product scale, enterprise authorization and broad vendor integrations remain out of scope until the v0.1 freeze is explicitly lifted.

## Operational invariant

While code-only validation mode is active, merge decisions are based on current-main freshness plus complete static diff/code review. Do not use GitHub Actions or automated tests, and do not claim runtime qualification that was not executed.
