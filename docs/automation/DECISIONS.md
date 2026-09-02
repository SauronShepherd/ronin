# Autonomous build decisions

## ADR-AUTO-001 — Start from observable repository state

**Status:** accepted — 2026-09-02

The target specifications describe a unification of prior codebases, while the observable `SauronShepherd/ronin` repository initially contained only `LICENSE`. Autonomous work must not claim that historical Fakebrick defects were repaired in this repository when the affected code is absent.

Therefore the first implementation follows E0 and establishes executable quality boundaries. Historical review findings remain backlog requirements and will be revalidated if/when their relevant code or equivalent capabilities are introduced.

## ADR-AUTO-002 — Pure-domain I/O rule is executable from the first code commit

**Status:** accepted — 2026-09-02

The architecture specification forbids filesystem, network, subprocess, SQLite and environment access in domain layers. A stdlib AST gate is introduced before domain implementation grows. Its own test suite includes deliberate violations so a silently ineffective gate is detected early.

## ADR-AUTO-003 — The package dependency matrix is executable before the packages exist

**Status:** accepted — 2026-09-02

The technical specification defines a normative import matrix for `studio_core`, notebook, codegen, bridge, native, debug, runners, kernel, orchestrator, storage, server and CLI. The repository now encodes that matrix in `tools/architecture_gate.py` and rejects both forbidden edges and undeclared `studio_*` packages.

The first implementation remains a small in-repo AST gate rather than introducing `import-linter` immediately. This keeps the E0 dependency surface minimal while still making the exact architectural rule executable and testable. `import-linter` remains a candidate additional independent gate once several real packages exist; adopting it must strengthen verification rather than replace a working contract with configuration that is not negatively tested.

A dedicated `gates-negative` CI job is mandatory for these architecture rules. A gate that cannot demonstrate failure against a deliberate violation is not treated as evidence.

## ADR-AUTO-004 — Adapt mature SDP IR ideas into a stricter Ronin core

**Status:** accepted — 2026-09-02

`sdp-studio` already contains useful deterministic IR lowering, graph semantics and source-provenance concepts. Ronin reuses those ideas rather than reimplementing the data-engineering core from zero, but the canonical `studio_core` boundary is stricter: it has no Pydantic, filesystem, clock, randomness, database, Spark or provider dependency.

The first E1 slice introduces immutable `NodeId`, `Port`, `Node`, `Edge` and `Pipeline` primitives, canonical ordering, canonical JSON and explicit topology/port validation. Node identity is derived from semantic content plus a required stable `instance_key`. User-facing labels are excluded from identity so renames do not invalidate semantic identity/source-map relationships, while the instance key permits two otherwise identical nodes to remain distinct.

The IR is deliberately execution-agnostic. Spark, SQL, ML, GenAI and agent-specific behavior must enter through operator catalogs and adapters rather than becoming assumptions in the identity/topology model.

## ADR-AUTO-005 — Enforce 100% line and branch coverage once pure-domain behavior exists

**Status:** accepted — 2026-09-02

The test specification requires zero-exclusion 100% line/branch coverage for pure domain layers. Now that `studio_core` contains meaningful behavior, the repository enforces that requirement directly through pytest-cov. Hypothesis and randomized test ordering are included in the development test toolchain to exercise determinism and insertion-order invariants.

Coverage failures are treated as missing behavioral evidence, not as a reason to lower the threshold. The first E1 implementation added adversarial deserialization and converging-DAG tests until the full core gate passed.

## ADR-AUTO-006 — Project owns Git bindings and execution intent; adapters own vendor runtime semantics

**Status:** accepted — 2026-09-02

Ronin is explicitly multi-project. A project owns exactly one primary Git repository plus optional supporting repositories, and owns its desired execution profile. This makes repository/runtime selection a first-class product concept instead of a global application setting.

The design adapts useful ideas already present in `sdp-studio` (`ProjectMetadata`, environment overrides, `RuntimeProfile` and `RuntimeCapabilities`) but removes Pydantic/time/random/runtime-provider state from the pure core. Repository credentials are references only and HTTP remotes may not embed credentials.

Execution intent is split into an opaque adapter-owned `RuntimeProfileRef` and provider-neutral `CapabilityRequirement`s. This permits user-facing selections such as Fabric Runtime or Databricks Runtime/LTS while keeping the canonical domain free of provider-specific branches. Adapters discover concrete profiles and capabilities; later resolver code produces a resolved runtime snapshot for run evidence/replay.

A project may request strict profile resolution or compatible fallback. Compatible fallback may only relax preferred characteristics; all required capabilities remain mandatory.

Post-publication GitHub Actions verification is also mandatory operational policy: after updating `main`, the builder must inspect workflows for the published SHA and continue correcting any regression caused by the change until required Actions are green or the increment is reverted.

## ADR-AUTO-007 — Runtime discovery is adapter I/O; compatibility resolution is pure evidence

**Status:** accepted — 2026-09-02

The mature `sdp-studio` runtime code is useful evidence and a reuse source, but its probing layer necessarily reads environment state, invokes binaries and branches on concrete adapters. Those behaviors remain outside Ronin's pure domain.

Adapters advertise immutable `RuntimeProfile` snapshots containing an opaque profile reference, availability and provider-neutral capability name/value pairs. `studio_core` deterministically evaluates those snapshots against project execution intent and returns explicit per-requirement evidence. Required capability failures are never downgraded; preferred matches rank compatible fallback candidates, with stable adapter/profile ordering as a deterministic tie-breaker.

The initial portable constraint grammar supports exact strings plus `==`, `!=`, `>=`, `<=`, `>` and `<`, with comma-separated conjunctions. Ordered comparison is deliberately limited to numeric dotted versions. Provider-specific version/channel semantics must be normalized by adapters before advertisement instead of creating vendor branches in core.

This resolver does not provision compute, read credentials, probe runtimes or persist run state. A later adapter/runtime boundary will reuse hardened discovery and execution code from `sdp-studio` and persist the selected profile plus evaluation evidence in resolved-runtime snapshots for audit/replay.

## ADR-AUTO-008 — Operator semantics are versioned pure data; discovery and execution hooks are boundaries

**Status:** accepted — 2026-09-02

Ronin reuses the mature `sdp-studio` operator-registry semantics but does not copy its entry-point discovery, mutable registry, compiler-hook strings or runtime-specific assumptions into `studio_core`.

The canonical operator model is immutable, provider-neutral and versioned by `OperatorRef`. It describes logical input/output ports, semantic parameter kinds, supported batch/stream modes and required/forbidden capability names. `OperatorCatalog` canonicalizes ordering and rejects duplicate versions. Node validation returns stable `OperatorViolation` evidence rather than invoking compilers or runtimes.

Plugin discovery, UI widget metadata, compiler implementations, schema inference, preview execution and provider-specific capability normalization belong outside the pure domain and will consume these contracts through replaceable boundaries. This keeps authored graphs portable while still allowing richer adapters and plugins to extend behavior.

The initial built-in catalog is intentionally a small portable seed adapted from proven `sdp-studio` operators. Adding an operator to the canonical seed requires semantic portability and golden-test evidence; engine/provider-specific operators may exist behind adapters without becoming canonical product assumptions.
