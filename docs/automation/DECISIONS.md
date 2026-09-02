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
