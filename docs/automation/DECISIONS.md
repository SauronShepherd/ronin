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

The test specification requires zero-exclusion 100% line and branch coverage for pure domain layers. Now that `studio_core` contains meaningful behavior, the repository enforces that requirement directly through pytest-cov. Hypothesis and randomized test ordering are included in the development test toolchain to exercise determinism and insertion-order invariants.

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

The minimum accepted mutation score is 90%. Ronin counts only killed mutants as positive evidence: `killed / (total - skipped)`. Survivors reduce the score, while `no_tests`, suspicious outcomes, timeouts, interrupted checks and segfaults make the evidence invalid and fail the gate. Production exclusions and `pragma: no mutate` escapes are not accepted as a way to reach the threshold. The target may be ratcheted upward as tests strengthen, but it must not be lowered merely to make CI pass.

Mutmut 3.x mutates code inside functions and methods; module-level executable code is outside its current mutation scope. Ronin records that limitation rather than pretending to cover it: normal tests, architecture checks and the independent 100% line/branch gate continue to protect the whole pure-domain package, and the mutation tool can be revisited when a stronger compatible option is available.

The repository uses a temporary `src -> python` source alias only inside the mutation job because mutmut's generated-mutant layout assumes a source root distinct from the project package directory. This is a tooling-boundary workaround, not a package-layout or domain-architecture change. Mutation runs select the pure-domain behavioral test files explicitly and clear pytest's global coverage addopts so mutants are killed by behavioral assertions, not by coverage-plugin side effects; the normal `quality` job still runs every test with full coverage enforcement.

Initial mutation evidence was 1,599 killed and 508 survived out of 2,107 total (75.89%), with no invalid categories. Rather than weaken the threshold, Ronin added complete deterministic snapshots for the built-in provider-neutral operator and diagnostic catalogs plus exact metadata-boundary assertions. The resulting evidence is 1,899 killed and 208 survived out of 2,107 total (90.13%), again with zero invalid categories. CI retains the compact exported counts and survivor list as a short-lived artifact so the gate is auditable even when log transport is truncated.

A reuse search across `SauronShepherd/sdp-studio` and `SauronShepherd/ronin-old` did not surface mutation-testing machinery suitable for reuse, so this quality boundary is implemented directly in Ronin.

## ADR-AUTO-013 — Notebook execution dependencies are explicit pure intent

**Status:** accepted — 2026-09-03

The canonical notebook document separates presentation order from execution intent. Executable `code` and `sql` cells may declare explicit dependencies on other executable cells; Markdown remains document content and cannot enter the execution DAG. Independent executable cells use authored order only as a deterministic tie-breaker.

`studio_notebook` performs no filesystem, network, subprocess, environment, kernel or provider work. Its dependency analyzer returns a complete deterministic execution order and parallel levels only for a valid graph; unknown dependencies, dependencies on non-executable cells and cycles fail closed with stable evidence and no partial plan.

The core does not infer hidden dependencies by parsing Python, SQL, Scala or vendor-specific notebook magics. Authoring/import adapters may propose dependency changes, but canonical execution intent changes only through an explicit document update that can be reviewed and versioned.

`ronin-old` provides useful prior semantics for `%%sql`, `%%configure` and `%pip`, but its implementation mutates notebook cells and can invoke subprocesses. Those behaviors are not copied into the pure domain. Future `studio_kernel`/adapter work may adapt the useful parsing semantics behind typed execution requests, permissions, audit/evidence, resource/cost attribution and reproducibility controls.

## ADR-AUTO-014 — Runtime discovery is a typed adapter SPI; selection evidence is immutable core data

**Status:** accepted — 2026-09-03

Ronin now makes the runtime-discovery boundary executable rather than leaving it as an architectural promise. `studio_runners` owns the side-effecting `RuntimeDiscoveryAdapter` SPI and normalizes adapter-owned profile advertisements into the existing provider-neutral `RuntimeProfile`/`RuntimeCatalog` contracts. Adapter IDs are unique, discovery runs in stable adapter order, and every advertised profile must belong to the reporting adapter.

Operational discovery failures do not cross the boundary as raw provider exceptions. The coordinator emits stable `runtime.discovery_failed` evidence without embedding `str(exc)`, so tokens, connection strings or other provider details accidentally present in exception text are not copied into canonical evidence. Adapters may return additional normalized issues, but they are responsible for redaction before doing so. Provider-specific probing, environment access, subprocesses, SDK calls and version/channel parsing remain outside `studio_core`.

A successful pure `RuntimeResolution` can now be frozen as `ResolvedRuntimeSnapshot` before execution. The snapshot records the requested profile reference, the complete selected immutable `RuntimeProfile` capability advertisement, resolution policy, exact-versus-fallback selection, requirement checks and preferred-match count. It deliberately has no implicit clock, random ID, credential, provider configuration or mutable runtime handle. Inconsistent hand-built resolution objects fail closed rather than producing misleading audit evidence.

This adapts the mature `sdp-studio` separation between runtime adapters/probes and capability validation, plus its hardened secret/error handling, while rejecting its provider branches and untyped profile dictionaries as canonical Ronin domain state. Later execution evidence may attach repository revision, effective non-secret runtime configuration, package/image digests, resource/cost data and observability references around this snapshot without mutating authored project intent.

## ADR-AUTO-015 — Notebook cell identity is persisted provenance; runtime state is separate

**Status:** accepted — 2026-09-03

Portable Ronin notebooks use schema `ronin.notebook/v1` and deterministic JSON. A canonical cell persists both its `CellId` and a `CellIdentityAnchor` made from a bounded `authoring`/`import` boundary, a stable document namespace and a source-stable reference. Deserialization re-derives every ID and rejects mismatches, so copied/tampered IDs cannot silently detach identity from provenance. Identity is deliberately independent of mutable source text, cell position, clocks, randomness, runtime/provider metadata and execution outputs.

Import adapters own source-specific reference allocation. Nbformat 4.5+ persisted cell IDs are suitable references when present; older or foreign formats must allocate and persist an equivalent stable external reference at the adapter boundary. `studio_notebook` does not infer identity from list position because insertion/reordering would make unrelated edits rewrite identity. Duplicate import references, unknown dependency references and schema/key drift fail closed.

Authored notebook intent contains only ordered cells, source/language, explicit dependencies and identity provenance. Execution counters, outputs, timestamps, kernels, packages, provider configuration, credentials and mutable session state belong to later kernel/orchestrator evidence and must never be folded back into the authored document as a side effect of execution. This adapts the useful nbformat/persisted-cell-id behavior visible in `ronin-old` while rejecting its service/runtime mixing and mutable magic rewriting as canonical document behavior. `sdp-studio` did not expose a stronger reusable canonical notebook model for this slice.

## ADR-AUTO-016 — Kernel preparation is adapter-owned; execution evidence surrounds authored intent

**Status:** accepted — 2026-09-03

`studio_kernel` is the typed boundary between immutable notebook intent and side-effecting execution adapters. A prepared notebook execution binds the exact `NotebookDocument`, a successful immutable `ResolvedRuntimeSnapshot`, and a `RepositoryRevision` containing the Git object ID plus an optional dirty-patch SHA-256. It does not rewrite any of those inputs or invent clocks, random attempt IDs, credentials or provider state.

Language- and magic-specific interpretation belongs to `KernelRequestAdapter`. An adapter may translate constructs such as `%pip`, `%%sql` or future provider syntax into an `executable_source` plus a normalized `KernelDirective` and explicit permission requirements, while the request retains the original authored source independently. Preparation fails closed if dependencies are invalid, the adapter changes `CellId`, or the directive claims a different adapter identity. This preserves reviewable authored semantics while permitting provider-specific execution behavior behind replaceable adapters.

Per-cell results are immutable normalized outcomes (`succeeded`, `failed`, `cancelled`). Raw provider exceptions do not become canonical failure state; failed results require a stable failure code. Cross-cutting execution artifacts are represented by typed references for logs, metrics, traces, lineage, outputs, resource usage and cost so later storage/observability systems can remain replaceable. Actual kernel/session I/O, cancellation, isolation, secret resolution, permission enforcement, redaction and durable event persistence remain future adapter/orchestrator responsibilities.

The design uses `ronin-old` only as behavioral evidence for useful notebook-magic concepts and deliberately rejects its mutable cell rewriting and direct subprocess behavior as the canonical contract. No stronger reusable kernel contract was found in the inspected `sdp-studio` material for this slice.

## ADR-AUTO-017 — Effective runtime reproducibility is immutable execution evidence, not authored intent

**Status:** accepted — 2026-09-03

A prepared execution carries an explicit `ExecutionAttemptId` plus an immutable `ExecutionReproducibilitySnapshot`. Attempt identity is allocated by the orchestration boundary and passed into `studio_kernel`; the canonical contract does not manufacture clocks, randomness or provider handles. Durable events derive identity from that attempt plus a non-negative sequence so storage/replay layers can preserve a stable total order without embedding wall-clock behavior in the domain.

Effective runtime configuration is evidence produced after adapter resolution, not project or notebook authoring state. Adapters must normalize values before crossing the boundary and must never pass resolved secrets. `EffectiveRuntimeSetting` intentionally rejects names that look like common credential/token/password/API-key/private-key material as a second fail-closed defense, but this check is not a substitute for adapter-side secret classification and redaction. Raw environment dumps, provider configuration objects and credentials are not canonical execution evidence.

Reproducibility artifacts use typed SHA-256 identities for package locks, environments, runtime images and runtime artifacts. The canonical contract stores a stable reference plus digest; acquiring bytes, resolving container repository digests, hashing artifacts and verifying remote/provider state remain adapter responsibilities. Duplicate setting names and duplicate digest kind/reference pairs fail closed so evidence cannot silently become ambiguous.

This adapts proven ideas from `sdp-studio` artifact hashing/runtime-profile safety and `ronin-old` secret-redaction and immutable base-image inspection without copying provider-specific execution or mutable runtime state into the canonical model. The next execution slice should consume these contracts through a real session adapter with cancellation, isolation, permission checks, redacted durable event emission and resource/cost/trace linkage.

## ADR-AUTO-018 — Session controls gate side effects; concrete executors prove isolation

**Status:** accepted — 2026-09-03

Prepared notebook intent and reproducibility evidence are not sufficient authorization to execute code. `KernelExecutionSession` is therefore the fail-closed operational control boundary between an immutable `NotebookExecutionRequest` and a side-effecting `KernelCellExecutor`.

The session validates an explicit `SessionPolicy` before delegating side effects. Required directive permissions are checked before the executor receives a cell. The default policy accepts only container or Kubernetes isolation and requires a dedicated identity plus network and filesystem isolation; process execution is an explicit opt-in. `ExecutorIsolation` records adapter assertions, not proof. Every concrete executor must be separately qualified with integration/adversarial tests that demonstrate the isolation it claims.

Cancellation is represented by a small signal protocol so local, container, Kubernetes and future remote executors can implement interruption without provider-specific branches in the canonical notebook model. Executor crashes are normalized to `kernel.executor.error`; raw exception text is not persisted as failure evidence. Executor results must preserve the requested `CellId`.

Operational evidence is ordered by the existing `ExecutionAttemptId` plus contiguous `ExecutionEventId.sequence`. Event messages are redacted before storage. The first local sink is append-only canonical JSONL with flush and fsync on every event, rejects mixed attempts and sequence gaps, and requires no external service. It is intentionally replaceable: restart/resume and shared durable stores remain later sink implementations.

This adapts `ronin-old` redaction and hardened session/pod concepts and `sdp-studio` typed event-envelope semantics without copying mutable notebook rewriting, direct subprocess execution or provider-specific lifecycle into the canonical boundary. The concrete local/container launcher remains a separate adapter task tracked by issue #16.

## ADR-AUTO-019 — Restart-safe JSONL is a single-writer recovery baseline, not workload resume

**Status:** accepted — 2026-09-04

The local JSONL execution-event sink must be able to reopen durable evidence after a process restart without silently duplicating or mixing event identities. On construction it therefore scans an existing complete ledger, validates the full persisted event shape and semantics, enforces one `ExecutionAttemptId` with a contiguous sequence starting at zero, and restores the next append sequence. A partial final write, malformed or semantically invalid event, mixed attempt, or sequence gap fails closed before further evidence is appended.

This guarantee is deliberately narrower than execution resume. `KernelExecutionSession` still owns in-memory progression through prepared cells and starts its own event sequence at zero; reopening a sink does not by itself reconstruct executor state, infer which side effects completed, or make a workload safe to rerun. A future resumable execution protocol must combine durable state-machine/checkpoint evidence with idempotency rules and explicit replay semantics rather than treating an appendable log as proof that side effects can be repeated.

The JSONL sink is also explicitly single-writer. `flush` plus `fsync` gives local durability for a completed append but does not provide cross-process mutual exclusion, leases, compare-and-swap, or transactional uniqueness. Shared/distributed event storage must guarantee that `(attempt_id, sequence)` remains unique under concurrent writers through an appropriate storage contract. Those guarantees belong behind the replaceable event-sink boundary rather than adding filesystem-locking assumptions to the canonical kernel domain.

## ADR-AUTO-020 — Concrete container execution is a runner adapter; isolation claims require qualification

**Status:** accepted — 2026-09-04

`studio_kernel` remains the provider-neutral execution/session contract and must not contain Docker, Kubernetes, subprocess or container-engine lifecycle logic. Concrete launchers live in the side-effecting `studio_runners` adapter layer, which may depend one-way on `studio_kernel` contracts. The executable architecture matrix therefore permits `studio_runners -> studio_kernel`; the reverse edge remains forbidden, preserving an acyclic contract-to-adapter boundary.

The first local container adapter uses Docker-compatible argument-array execution but models only neutral execution facts at the kernel boundary. It requires an immutable container image identity: either a repository digest (`repo@sha256:...`) or a local image ID (`sha256:...`). Supporting local image IDs is deliberate for offline/air-gapped use and avoids making a registry a prerequisite for reproducible local execution.

The adapter materializes a hardened baseline with an explicit non-root uid/gid, `--network none`, a read-only root filesystem, dropped Linux capabilities, `no-new-privileges`, PID/CPU/memory ceilings, and a bounded isolated tmpfs. Cancellation and timeout actively remove the named container rather than merely cancelling the caller. Operational output is bounded and redacted both by the command runner and again at the evidence-persistence boundary so a replaceable runner cannot bypass credential redaction.

These command-line controls justify an `ExecutorIsolation` assertion only as implementation intent. They are not production qualification evidence by themselves. Issue #16 remains open until integration/adversarial tests against a real container engine demonstrate the effective uid, network/filesystem/capability restrictions, cancellation cleanup and cgroup limits. Likewise, configured CPU/memory ceilings are recorded as limits, not observed usage; cost evidence must not be synthesized from limits. Observed resource accounting and provider-neutral local/showback cost evidence require a later qualified collector.

## ADR-AUTO-021 — Cycle participation means strongly connected dependency membership

**Status:** accepted — 2026-09-04

Notebook dependency diagnostics must distinguish a cell that actually participates in a directed cycle from a cell that is only transitively blocked by one. Residual positive indegree after Kahn-style topological processing is sufficient to prove that a complete execution plan cannot be produced, but it is not sufficient evidence that every residual cell belongs to a cycle.

`studio_notebook` therefore computes actual strongly connected components for residual executable cells and emits `dependency_cycle` only for cells in cyclic components. Downstream blocked cells remain excluded from cycle-participation evidence. The analyzer still fails closed and returns no partial execution order or levels when any cycle exists, preserving ADR-AUTO-013's execution-safety contract while making the diagnostic evidence precise and suitable for UI remediation, audit and future automated repair tooling.

The implementation is deterministic and provider-neutral: authored notebook order is used only to stabilize traversal and finding order, not to redefine graph semantics. An adversarial regression test covers a two-cell cycle with a multi-level downstream blocked chain.

## ADR-AUTO-022 — Execution sessions are single-use and durable evidence is defensively redacted at construction boundaries

**Status:** accepted — 2026-09-04

A `KernelExecutionSession` represents one execution attempt and is intentionally single-use. Re-entering the same in-memory session after it has started is rejected before isolation validation or event emission can cause a second set of side effects. Retry/resume semantics must therefore be modeled explicitly by future orchestrator Job/Run/Attempt state rather than by calling `run()` twice on the same session object.

Secret prevention remains a layered responsibility. Adapters must avoid placing credentials in operational text, but durable kernel evidence also applies centralized defensive redaction to event messages, evidence references and normalized failure codes. The redactor covers named secret fields, bearer credentials, common provider-token shapes, JWT-like values, PEM private keys and URI user-info credentials. This is defense in depth, not a guarantee that arbitrary unknown secret formats can safely enter evidence.

Unexpected executor exceptions remain normalized to `kernel.executor.error`. The session may persist only the exception type name as bounded operational context; arbitrary exception messages are deliberately discarded because they commonly contain connection details, provider errors or secrets. This strengthens ADR-AUTO-018 without changing the provider-neutral kernel/runner boundary or upgrading any container isolation assertion into proof.

## ADR-AUTO-023 — Review findings are reconciled against the current trust boundary before closure

**Status:** accepted — 2026-09-04

External or continuous reviews are evidence tied to the exact repository SHA they analyzed, not timeless statements about `main`. Before implementing or closing a finding, Ronin reconciles the reviewed SHA against current `main`, recent verified changes, open issues/PRs and the executable architecture contracts. A finding already fixed on a newer exact SHA is recorded as superseded rather than reimplemented; a still-valid finding remains open until direct evidence proves it.

When an already-validated PR contains the needed implementation but is based on stale history, Ronin reuses the validated product/test changes on current `main` rather than merging the stale branch wholesale. Current contracts introduced later must be preserved deliberately. In particular, the strengthened pure-domain architecture gate from the earlier hardening work is integrated while retaining ADR-AUTO-020's current one-way `studio_runners -> studio_kernel` dependency required by the concrete container adapter.

Security/release language must distinguish repository code from repository administration. A CI workflow can require checks and validate release provenance, but it cannot make `main` or a tag immutable by itself. Branch/tag rulesets are therefore a required governance control and may only be marked implemented when GitHub reports them active; absence of administration capability in an automation connection is a blocker, not permission to fabricate an equivalent claim.

Likewise, declared container isolation and configured resource ceilings remain different from qualified/observed facts. The architecture will evolve toward typed, versioned isolation qualification and observed attempt evidence, but the current Docker adapter remains unqualified until real-engine tests close issue #16.