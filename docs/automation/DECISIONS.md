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

## ADR-AUTO-009 — Diagnostics match normalized facts; provider error parsing stays in adapters

**Status:** accepted — 2026-09-02

The mature `sdp-studio` diagnostic catalog provides useful failure categories, checks and remediation, but its canonical matcher loads YAML-defined regular expressions and the shipped rules encode Spark and Kubernetes error syntax. Ronin reuses the semantic categories and actionable guidance without moving those provider/runtime assumptions into `studio_core`.

Adapters and validation layers emit bounded immutable `DiagnosticFact` values using provider-neutral categories plus optional normalized code, message and source evidence. The pure core matches facts using a deliberately small grammar of equality, substring containment and prefix predicates. Rules are immutable data, predicates compose with deterministic AND semantics, and `DiagnosticCatalog` canonicalizes rule order and emits stable `DiagnosticFinding` evidence.

Arbitrary regular expressions, YAML loading, provider log parsing, runtime I/O and vendor-specific rule packs are not part of the canonical domain. Adapter-specific parsers may translate raw Spark, Kubernetes, Databricks, Fabric or future provider errors into the same neutral fact categories, preserving portability while allowing rich runtime diagnostics.

The built-in catalog is intentionally a portable seed adapted from proven `sdp-studio` failure classes such as unresolved schema fields, type mismatches, resource exhaustion, unsupported capabilities, execution-mode mismatch, missing dependencies, access denial and shared-state mutation. Adding canonical rules requires provider-neutral semantics plus golden-test evidence.

## ADR-AUTO-010 — Portable project intent is deterministic JSON; workspace auth stays outside it

**Status:** accepted — 2026-09-02

Ronin adopts a single repository-local project manifest at `.ronin/project.json`, identified by schema `ronin.project/v1`. The core representation is immutable and serializes with deterministic ordering. Parsing is strict: unknown or missing v1 keys fail rather than being silently ignored, so schema evolution must be explicit.

The manifest records project identity, primary/supporting Git repository intent, opaque repository adapter IDs, default refs, optional repository-relative subdirectories, sync policy, runtime-profile intent, capability requirements and execution resolution. Git synchronization is deliberately bounded to `manual`, `fetch`, or `fast-forward`; automatic merge/rebase semantics are not canonical project behavior.

Workspace-only state is not committed. Repository `auth_ref` values remain valid on workspace `Project` objects but `ProjectManifest.from_project()` strips them, and local checkout paths, resolved credentials/tokens, runtime discovery snapshots and execution results remain application/storage concerns. A remote URI is portable repository identity and may remain in the manifest as long as it contains no embedded credentials.

This adapts the versioned project-metadata and environment-reference ideas from `sdp-studio` without importing its Pydantic models, YAML/filesystem persistence, provider-specific environment overrides, clock/random defaults, or resolved runtime state into `studio_core`. File I/O and future on-disk migrations must be implemented outside the pure domain.

## ADR-AUTO-011 — Stable node identity requires persisted authoring/import provenance

**Status:** accepted — 2026-09-02

A pure graph-structure rule cannot assign stable distinct identities to two automorphic or otherwise structurally identical nodes without introducing an arbitrary traversal/order tie-breaker. Ronin therefore treats stable instance identity as provenance supplied by the boundary that owns the source document, not as something invented by graph canonicalization.

`InstanceAnchor` is the canonical pure contract for that provenance. Its bounded `authoring` and `import` origins pair with a caller-supplied stable reference; `studio_core` deterministically derives an `instance_key` from the pair. Batch allocation rejects duplicate anchors rather than silently disambiguating with sequence numbers, clocks, randomness or current topology. Editors/importers remain responsible for choosing and persisting references that survive unrelated edits.

Canonical `Node` now persists `instance_key` alongside `NodeId`. Deserialization reconstructs the canonical semantic payload, re-derives the identifier, and rejects an ID/key/semantic mismatch. Labels, canvas coordinates, insertion order, graph traversal order and runtime/provider state remain outside identity.

This deliberately adapts `sdp-studio`'s useful property that document IDs are allocated before lowering and propagated through IR/source provenance. Ronin does not reuse `sdp-studio`'s ULID generator inside `studio_core` because it reads wall-clock time and OS randomness. A future authoring adapter may use an opaque random ID implementation at its side-effect boundary; once allocated, the resulting stable anchor is persisted and passed explicitly into the pure domain.

## ADR-AUTO-012 — Mutation testing is an independent semantic quality gate

**Status:** accepted — 2026-09-03

`studio_core` keeps its mandatory 100% line and branch coverage gate with zero exclusions. Mutation testing supplements that evidence; it never replaces or weakens coverage. The mutation gate is pinned to `mutmut==3.7.0` because mutation behavior and the exported CI evidence schema are themselves part of the quality contract.

The minimum accepted mutation score is 90%. Ronin counts only killed mutants as positive evidence: `killed / (total - skipped)`. Survivors reduce the score, while `no_tests`, `suspicious`, `timeout`, interrupted checks and segfaults make the evidence invalid and fail the gate. Production exclusions and `pragma: no mutate` escapes are not accepted as a way to reach the threshold. The target may be ratcheted upward as tests strengthen, but it must not be lowered merely to make CI pass.

Mutmut 3.x mutates code inside functions and methods; module-level executable code is outside its current mutation scope. Ronin records that limitation rather than pretending to cover it: normal tests, architecture checks and the independent 100% line/branch gate continue to protect the whole pure-domain package, and the mutation tool can be revisited when a stronger compatible option is available.

The repository uses a temporary `src -> python` source alias only inside the mutation job because mutmut's generated-mutant layout assumes a source root distinct from the project package directory. This is a tooling-boundary workaround, not a package-layout or domain-architecture change. Mutation runs select the pure-domain behavioral test files explicitly and clear pytest's global coverage addopts so mutants are killed by behavioral assertions, not by coverage-plugin side effects; the normal `quality` job still runs every test with full coverage enforcement.

Initial mutation evidence was 1,599 killed and 508 survived out of 2,107 total (75.89%), with no invalid categories. Rather than weaken the threshold, Ronin added complete deterministic snapshots for the built-in provider-neutral operator and diagnostic catalogs plus exact metadata-boundary assertions. The resulting evidence is 1,899 killed and 208 survived out of 2,107 total (90.13%), again with zero invalid categories. CI retains the compact exported counts and survivor list as a short-lived artifact so the gate is auditable even when log transport is truncated.

A reuse search across `SauronShepherd/sdp-studio` and `SauronShepherd/ronin-old` did not surface mutation-testing machinery suitable for reuse, so this quality boundary is implemented directly in Ronin.
