# Autonomous build backlog

Items are ordered by the construction plan and by risk. Selection is always revalidated against the real repository state before implementation.

## E0 — Foundation

Completed:

- Executable pure-domain I/O boundary.
- Executable package dependency matrix for all planned `studio_*` layers.
- Dedicated negative-gate harness proving deliberate I/O, environment and layer violations fail.
- Ruff, strict mypy, pytest and CI baseline.
- Fail-closed pure-domain architecture inspection rejects unknown non-stdlib imports, nondeterministic imports/calls, filesystem/process/environment effects and invalid Python syntax rather than relying on a narrow side-effect denylist.
- Pull-request CI cancels obsolete runs while `main` push validation is never cancelled, reducing stale evidence without weakening publication checks.

Still required:

1. Add secret and dependency security gates (`gitleaks`, dependency audit) with negative fixtures where practical.
2. Add documentation/governance contracts and ASF-ready community files without claiming current ASF status.
3. Add manifest validation only when Kubernetes/Compose/Helm artifacts enter the repository; do not create placeholder infrastructure merely to satisfy a gate.
4. Evaluate augmenting the in-repo dependency gate with `import-linter` once multiple real packages exist. The negatively-tested AST gate remains authoritative until an additional tool proves equivalent or stronger coverage.
5. Protect `main` and release tags through GitHub repository rulesets: require pull requests and mandatory checks on `main`, block force-push/deletion, and make release tags immutable. This is repository administration, not an in-code substitute; it must not be marked implemented until the repository reports the rules as active.

## E1 — Core IR and project domain

Completed:

- Immutable `NodeId`, `Port`, `Node`, `Edge` and `Pipeline` primitives.
- Canonical node/edge ordering independent of insertion order.
- Stable semantic node identity using semantic content plus an explicit stable instance key; labels do not affect identity.
- Stable `InstanceAnchor` allocation contract for authoring/import boundaries, persisted `instance_key` evidence in canonical IR, identity verification during deserialization, and symmetric-graph invariants that do not depend on traversal order.
- Canonical JSON serialization/deserialization with deterministic round-trip behavior.
- Edge validation for unknown nodes, exact ports, batch/stream compatibility, schema compatibility and cycles.
- IR boundary hardening rejects non-finite numeric values, prevents invalid direct `Node` construction, uses total deterministic port ordering and keeps semantic identity explicitly typed rather than relying on presentation or insertion state.
- Hypothesis properties, adversarial deserialization tests and 100% line/branch coverage for `studio_core`.
- Multi-project pure-domain contracts: `Project`, canonical `ProjectCollection`, primary/supporting Git repository bindings, secret/connection references, runtime profile references and provider-neutral capability requirements.
- Project/repository/runtime validation trims and validates user-controlled text, rejects credential-bearing repository URIs and Windows-absolute repository subdirectories, constrains capability-expression grammar, and keeps provider-specific ordered version strings out of core comparison semantics.
- Per-project execution intent supports exact adapter-owned runtime profiles and compatible capability-based resolution without vendor branches in the core.
- Provider-neutral `RuntimeProfile`/`RuntimeCatalog` advertisement snapshots and pure deterministic resolution with per-requirement compatibility evidence, required/preferred semantics, availability filtering and stable fallback ranking.
- Adapter-side `studio_runners` runtime discovery SPI with deterministic adapter ordering, normalized discovery issues, provider-failure containment, and canonical `RuntimeCatalog` assembly; immutable `ResolvedRuntimeSnapshot` evidence freezes the selected profile and compatibility checks before execution without clocks, secrets or provider configuration entering `studio_core`.
- Versioned provider-neutral operator contracts for ports, semantic parameters, modes and required/forbidden capabilities; deterministic `OperatorCatalog`, stable validation evidence and a portable seed catalog adapted from mature `sdp-studio` semantics with golden/adversarial tests.
- Provider-neutral diagnostic facts/rules/findings with a bounded non-regex predicate grammar, deterministic `DiagnosticCatalog` matching and a portable actionable seed adapted from mature `sdp-studio` failure categories with golden/adversarial tests; raw runtime/provider normalization stays outside `studio_core`.
- Portable `.ronin/project.json` schema with deterministic serialization/deserialization, provider-neutral Git adapter/default-ref/sync intent, and strict exclusion of machine-specific auth bindings from committed project configuration.
- Mutation testing for `studio_core` with pinned `mutmut==3.7.0`, auditable CI evidence, a strict 90% minimum score, and complete portable seed-contract snapshots; verified score is 1,899 killed / 2,107 total = 90.13%, with 208 survivors and zero invalid-evidence categories, while the independent 100% line/branch coverage gate remains mandatory.
- Immutable `studio_notebook` cells with explicit executable-cell dependencies, deterministic topological execution order/parallel levels, fail-closed cycle/unknown/non-executable dependency evidence, and Markdown kept outside execution semantics. The 100% line/branch coverage and strict typing gates now include `studio_notebook`.
- Notebook cycle diagnostics identify only cells that are actual members of a directed dependency cycle; cells merely blocked downstream are excluded from cycle-participation evidence, with adversarial cycle-plus-blocked-chain regression coverage.
- Portable `ronin.notebook/v1` deterministic JSON with persisted/verifiable `CellIdentityAnchor` provenance, stable authoring/import IDs, strict unknown-field/schema rejection, pure import mapping from source-stable cell references and explicit exclusion of runtime outputs/metadata from authored notebook intent.
- Typed `studio_kernel` execution-evidence boundary with immutable notebook/runtime/repository-bound requests, adapter-owned source/magic preparation that must preserve cell identity, normalized per-cell outcomes, explicit permission requirements and typed log/metric/trace/lineage/output/resource/cost references. Authored notebook source is never mutated by preparation.
- Immutable execution reproducibility snapshots bound to an explicit durable attempt ID, with deterministic event identities, adapter-normalized effective non-secret settings, and typed SHA-256 identities for package locks, environments, runtime images and runtime artifacts. Secret-looking setting names and duplicate evidence keys fail closed; authored project/notebook intent remains unchanged.
- Fail-closed `KernelExecutionSession` controls around concrete executors: cancellation signals, exact permission checks before side effects, explicit isolation-policy validation, normalized executor-crash failures, automatic operational-text redaction and contiguous per-attempt events. The initial local durable sink is append-only JSONL with flush+fsync per event; actual process/container/Kubernetes launch remains behind `KernelCellExecutor` and must truthfully satisfy the declared isolation facts.
- Kernel sessions are single-use so a caller cannot accidentally replay side effects/events by invoking the same session twice. Defensive redaction is centralized across operational events, evidence references and failure codes, covering named secrets, bearer/JWT/provider tokens, PEM private keys and URI credentials; executor exception types may be retained as bounded diagnostics while arbitrary exception messages are never persisted.
- Restart-safe single-writer JSONL event-ledger recovery: an existing attempt is recovered with its next sequence, while partial writes, invalid JSON/event shapes, mixed attempts and non-contiguous sequences fail closed before any append. Multi-writer/shared-storage arbitration remains a later storage concern.
- First concrete hardened local-container executor adapter in `studio_runners`: immutable image digest/image-id input, non-root identity, network-none/read-only filesystem, dropped capabilities, no-new-privileges, PID/CPU/memory ceilings, isolated tmpfs, hard cancellation/timeout cleanup, normalized outcomes, replaceable evidence storage, and redacted log plus duration/configured-limit resource evidence.
- Real Docker-engine qualification for issue #16: a dedicated CI job executes the hardened adapter against Docker and verifies effective uid/gid 65532, loopback-only networking, read-only rootfs with bounded writable tmpfs, zero effective capabilities, `NoNewPrivs=1`, effective cgroup CPU/memory/PID ceilings, cancellation/timeout cleanup with no residual containers, and observed cgroup CPU/memory usage. The qualification records the immutable executed image ID plus bootstrap repository digest and explicitly emits no currency cost when a local price basis is unknown rather than inventing showback from configured limits.

Next:

1. Replace free-form isolation authorization facts with a typed, versioned Ronin isolation claim that distinguishes requested policy, declared adapter properties, qualification status/scheme/runtime identity/evidence, and observed attempt evidence. Production policy must be able to require `QUALIFIED` based on independent qualification evidence rather than command-plan intent.
2. Move event-loop ownership out of `AsyncioCommandRunner.run()`: the command/executor port should be awaitable, and only an explicit outer synchronous shell may bridge with `asyncio.run()`. Preserve a provider-neutral kernel contract while preparing for an async control plane.
3. Extend mutation qualification to high-risk `studio_kernel` and `studio_runners` behavior first, then `studio_notebook`. Keep the current `studio_core` >=90% gate and 100% line/branch coverage unchanged; establish package-specific baselines from real mutation evidence and ratchet upward rather than inventing a passing threshold.
4. Add crash/restart state-machine qualification spanning session, executor result, event append, evidence persistence and cleanup. Terminal state must be unique/monotonic and recovery must not double-finalize or duplicate durable identity.
5. Add at least one true notebook -> kernel -> real runtime -> durable evidence -> restart/recovery E2E journey now that the real Docker boundary is qualified.
6. Add a concrete runtime-evidence collector adapter that derives effective non-secret settings and verifies package/environment/image/artifact digests from real local/container execution without putting provider logic into `studio_kernel`.
7. Evolve event persistence from the restart-safe single-writer JSONL baseline toward shared durable storage semantics with explicit writer arbitration/lease or transactional append guarantees; never permit duplicate `(attempt_id, sequence)` identities under concurrent writers.
8. Introduce explicit Ronin `Job -> Run -> Attempt` orchestration semantics for retry/replay/idempotency before adding distributed scheduling. A retry must create a new attempt; it must never reuse one execution session.
9. Integrate the already-validated distribution/public-contract work from PR #21 onto current `main`, then add a clean-room build/install smoke for the root `ronin-studio` artifact as distinct evidence from `pyronin` packaging.
10. Add bounded deterministic performance guards for notebook DAG analysis, ledger replay and evidence persistence without destructive load testing.
11. Add a real temporary-Git adapter qualification when the concrete repository adapter lands: object identity, dirty patch digest, detached HEAD/ref movement and credential/path safety.
12. Add an optional OTLP/OpenTelemetry exporter behind Ronin-native evidence/event semantics. OTLP is transport/correlation only; Ronin keeps canonical attempt, evidence, lineage, policy, redaction, retention and cost semantics.
13. Ratchet mutation quality upward when new tests make that sustainable; never lower an existing threshold merely to make CI pass.

## Later reuse

- Reuse/adapt `sdp-studio` codegen, source maps, runners, debug, collaboration, auth/scheduling, React/XYFlow/Monaco and deployment work behind Ronin boundaries.
- Reuse `sdp-studio` runtime capability discovery and environment concepts behind the new neutral project/execution contracts rather than retaining vendor booleans in the core.
- Selectively reuse `ronin-old` native execution/Gluten/Velox and hardened redaction/session ideas; do not revive its monolithic API/controller architecture.
- Treat OpenTelemetry/OTLP, gVisor and Kata as replaceable ecosystem integrations/qualification targets, never as canonical Ronin domain semantics.

## Operational invariant

After every publication/deployment to `main`, inspect the GitHub Actions runs for that SHA. A builder execution is not complete while mandatory workflows are still running or failing. Fix regressions and republish/recheck until green; if the increment cannot safely be made green, revert it rather than weakening a gate.

## Security carry-over

The historical Fakebrick review contains P0/P1 findings (control-plane isolation, secrets, pod recreation, authorization and JWT validation). They remain requirements for E2, but none should be marked fixed until corresponding runtime code exists in this repository and regression tests prove the property.

The 2026-09-04 continuous-QA and architecture reviews were produced against historical SHA `23d27ecff31a4296723fd549875d0f044c1d2cc8`. Their findings are reconciled against current `main` before implementation: session single-use and durable redaction are already published; broader mutation, typed isolation qualification, release-root protection, security scans, state-machine/E2E evidence and clean release qualification remain tracked above until independently proven.
