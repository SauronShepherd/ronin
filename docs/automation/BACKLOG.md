# Autonomous build backlog

Items are ordered by the construction plan and by risk. Selection is always revalidated against the real repository state before implementation.

## E0 — Foundation

Completed:

- Executable pure-domain I/O boundary.
- Executable package dependency matrix for all planned `studio_*` layers.
- Dedicated negative-gate harness proving deliberate I/O, environment and layer violations fail.
- Ruff, strict mypy, pytest and CI baseline.

Still required:

1. Add secret and dependency security gates (`gitleaks`, dependency audit) with negative fixtures where practical.
2. Add documentation/governance contracts and ASF-ready community files without claiming current ASF status.
3. Add manifest validation only when Kubernetes/Compose/Helm artifacts enter the repository; do not create placeholder infrastructure merely to satisfy a gate.
4. Evaluate augmenting the in-repo dependency gate with `import-linter` once multiple real packages exist. The negatively-tested AST gate remains authoritative until an additional tool proves equivalent or stronger coverage.

## E1 — Core IR and project domain

Completed:

- Immutable `NodeId`, `Port`, `Node`, `Edge` and `Pipeline` primitives.
- Canonical node/edge ordering independent of insertion order.
- Stable semantic node identity using semantic content plus an explicit stable instance key; labels do not affect identity.
- Stable `InstanceAnchor` allocation contract for authoring/import boundaries, persisted `instance_key` evidence in canonical IR, identity verification during deserialization, and symmetric-graph invariants that do not depend on traversal order.
- Canonical JSON serialization/deserialization with deterministic round-trip behavior.
- Edge validation for unknown nodes, exact ports, batch/stream compatibility, schema compatibility and cycles.
- Hypothesis properties, adversarial deserialization tests and 100% line/branch coverage for `studio_core`.
- Multi-project pure-domain contracts: `Project`, canonical `ProjectCollection`, primary/supporting Git repository bindings, secret/connection references, runtime profile references and provider-neutral capability requirements.
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
- First concrete hardened local-container executor adapter in `studio_runners`: immutable image digest/image-id input, non-root identity, network-none/read-only filesystem, dropped capabilities, no-new-privileges, PID/CPU/memory ceilings, isolated tmpfs, hard cancellation/timeout cleanup, normalized outcomes, replaceable evidence storage, and redacted log plus duration/configured-limit resource evidence. These are implementation contracts and command-plan evidence; production-safe isolation still requires real-engine qualification.

Next:

1. Finish issue #16 by qualifying the container executor against a real Docker engine: adversarially prove effective non-root/network/filesystem/capability isolation, cancellation cleanup and configured cgroup ceilings, then collect observed CPU/memory usage and provider-neutral cost/showback evidence where meaningful. Do not promote configured limits into observed-usage claims.
2. Add a concrete runtime-evidence collector adapter that derives effective non-secret settings and verifies package/environment/image/artifact digests from real local/container execution without putting provider logic into `studio_kernel`.
3. Evolve event persistence from the restart-safe single-writer JSONL baseline toward shared durable storage semantics with explicit writer arbitration/lease or transactional append guarantees; never permit duplicate `(attempt_id, sequence)` identities under concurrent writers.
4. Ratchet mutation quality upward when new tests make that sustainable; never lower the threshold merely to make CI pass.

## Later reuse

- Reuse/adapt `sdp-studio` codegen, source maps, runners, debug, collaboration, auth/scheduling, React/XYFlow/Monaco and deployment work behind Ronin boundaries.
- Reuse `sdp-studio` runtime capability discovery and environment concepts behind the new neutral project/execution contracts rather than retaining vendor booleans in the core.
- Selectively reuse `ronin-old` native execution/Gluten/Velox and hardened redaction/session ideas; do not revive its monolithic API/controller architecture.

## Operational invariant

After every publication/deployment to `main`, inspect the GitHub Actions runs for that SHA. A builder execution is not complete while mandatory workflows are still running or failing. Fix regressions and republish/recheck until green; if the increment cannot safely be made green, revert it rather than weakening a gate.

## Security carry-over

The historical Fakebrick review contains P0/P1 findings (control-plane isolation, secrets, pod recreation, authorization and JWT validation). They remain requirements for E2, but none should be marked fixed until corresponding runtime code exists in this repository and regression tests prove the property.