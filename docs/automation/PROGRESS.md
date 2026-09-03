# Autonomous build progress

## Current stage

**E1 — Core IR and project domain**

The repository began with only `LICENSE`. Work first established executable foundations; product behavior is now entering the pure domain incrementally and remains subject to the same gates.

## 2026-09-02 — Foundation baseline

Completed in this increment:

- Added the Python package layout rooted at `python/` with `studio_core` as the first pure-domain package.
- Added Ruff, mypy strict and pytest configuration in `pyproject.toml`.
- Added an executable AST-based pure-domain I/O architecture gate.
- Added negative tests proving the gate catches forbidden SQLite/file access and environment access.
- Added a GitHub Actions quality workflow covering format, lint, strict typing, architecture contracts and tests.
- Added `Makefile`, repository status README, durable backlog and decision log for subsequent autonomous runs.

Publication history and evidence:

1. `9d9e55f812946b06792cc1ece8c627206c6e37bc` — initial E0 foundation. CI correctly failed at lint.
2. `83dad35bd1c3688310ca6add34c84de770eb8d70` — converted architecture tests to pytest style, explicitly allowed test assertions for Bandit rule S101, and fixed modern typing import. CI passed format, lint, mypy and architecture, then exposed a pytest import-path issue.
3. `a55d58a128c9bcf2b5f253756cf4a43951beb379` — made test invocation deterministic with `python -m pytest`. This is the final verified product-code SHA for the first execution.

Verified gates on `a55d58a128c9bcf2b5f253756cf4a43951beb379`:

- GitHub Actions `Format`: success.
- GitHub Actions `Lint`: success.
- GitHub Actions `Types` (`mypy` strict): success.
- GitHub Actions `Architecture contracts`: success.
- GitHub Actions `Tests`: success.

## 2026-09-02 — Package dependency contracts and negative gates

Completed in this increment:

- Extended `tools/architecture_gate.py` from a pure-I/O check into the executable package-dependency matrix defined by the technical architecture.
- Declared allowed imports for `studio_core`, notebook, codegen, bridge, native, debug, runners, kernel, orchestrator, storage, server and CLI layers before those packages are implemented.
- Added explicit failures for undeclared `studio_*` packages and unknown project imports.
- Hardened pure-domain I/O detection to catch environment access through aliases/from-imports.
- Added a dedicated negative-gate CI job proving deliberate architecture violations fail.
- Expanded architecture tests and made repository tooling strict-typed.

Verified on `94c01b16b4eb4e8994928192272585d2d267f217` and recorded on documentation SHA `66cc9c7fe9950a4f151286f10a6a1db4700a069c`: quality and gates-negative jobs succeeded without weakening rules.

## 2026-09-02 — E1 canonical immutable IR

Objective: introduce the first meaningful product-domain behavior by adapting the strongest IR ideas already present in `sdp-studio` into Ronin's stricter pure, provider-neutral core.

Implemented:

- `python/studio_core/ids.py`: deterministic `NodeId` derived from semantic content plus an explicit stable instance key, without clock/random/environment dependencies.
- `python/studio_core/ir.py`: immutable `SchemaRef`, `Port`, `OperatorRef`, `Origin`, `Node`, `Edge`, `PipelineConfig` and `Pipeline` contracts.
- JSON-compatible values are frozen into recursively immutable/canonical structures before entering domain objects.
- Nodes canonicalize params and ports; pipelines canonicalize node/edge insertion order.
- Pipeline validation rejects duplicate identities, unknown nodes, ambiguous/missing ports, batch/stream incompatibility, incompatible schemas and cycles.
- Canonical JSON serialization/deserialization preserves typed metadata and deterministic ordering.
- Node labels are intentionally excluded from semantic identity; identical semantic nodes remain distinguishable through the required stable `instance_key`.
- `tests/test_core_ir.py` adds unit, adversarial and Hypothesis property tests, including random test ordering.
- `pyproject.toml` now enforces 100% line and branch coverage for `studio_core` with zero exclusions.

Validation history deliberately retained as evidence that gates are active:

1. Initial validation was rejected by canonical formatting.
2. The next pass found a function-call default and import-order issue; the default was redesigned around an immutable module constant rather than suppressed.
3. `mypy --strict` then exposed topology variable shadowing; variables were clarified instead of cast/suppressed.
4. All 28 functional tests initially passed but coverage was 91.99%; the 100% threshold was kept and missing adversarial/topology branches were tested.
5. Final pre-publication validation of product code passed format, lint, strict mypy, architecture contracts, gates-negative, Hypothesis/randomized tests and 100% line/branch coverage.

No issue was opened: every defect discovered by the gates was local to this increment and corrected before publication.

## 2026-09-02 — E1 multi-project Git and execution intent

Objective: make project context a first-class domain concept so Ronin can manage multiple projects, each with its own Git repository and execution/runtime intent, without turning Fabric, Databricks or any other provider into the canonical model.

Implemented:

- Added immutable `ProjectId`, `Project`, and canonical `ProjectCollection` contracts.
- Each project requires exactly one primary Git repository and may attach supporting repositories.
- Git bindings are hosting-neutral and include alias, URI, default ref, optional subdirectory, role and credential reference.
- Repository configuration rejects embedded HTTP credentials, literal auth material and repository-root path escapes.
- Added opaque adapter-owned `RuntimeProfileRef` plus provider-neutral `CapabilityRequirement` contracts.
- Execution intent can pin a concrete runtime profile, express capabilities only, or combine both; `strict` and `compatible` resolution policies are explicit.
- Capability requirements distinguish mandatory and preferred characteristics and are canonicalized deterministically.
- User-facing adapters may expose Fabric Runtime, Databricks Runtime/LTS, Spark local/Connect/Kubernetes or future profiles while `studio_core` remains free of vendor branches.
- Added `docs/product/PROJECTS_AND_EXECUTION.md` defining project switching, Git/runtime UX, future portable `.ronin/` configuration and resolved-runtime snapshots for audit/replay.
- Updated README, backlog and ADRs so multi-project repository/runtime selection is a permanent product requirement.

Validation evidence before publication:

- The temporary PR workflow caught formatter drift twice before the change reached `main`.
- Diagnostics isolated the remaining formatter mismatch to `tests/test_projects.py`; the repository's pinned Ruff version then generated the canonical formatting on the temporary validation branch.
- Temporary diagnostic workflow changes are not part of the publication candidate; the original read-only CI workflow is restored before full validation.
- No quality gate was weakened and no vendor-specific runtime behavior entered the pure core.

The next related slice is a pure execution-profile catalog/resolver: adapters advertise concrete profiles and capabilities, while deterministic core resolution returns compatibility evidence suitable for UI explanations and later run snapshots. Operator/diagnostic catalog migration from `sdp-studio` remains the adjacent E1 reuse priority.

## 2026-09-02 — E1 provider-neutral runtime profile resolution

Objective: close the project execution-intent loop with a pure catalog/resolver while reusing the mature capability/probing concepts in `sdp-studio` without importing its environment/subprocess/vendor coupling into the canonical domain.

Implemented on validation branch `automation/runtime-profile-resolver`:

- Added immutable `RuntimeCapability`, `RuntimeProfile` and canonical `RuntimeCatalog` snapshots for adapter-advertised runtime state.
- Added deterministic resolution for exact runtime requests, capability-only intent and compatible fallback.
- Required capabilities are never relaxed; preferred requirements affect ranking only.
- Unavailable profiles are evaluated for evidence but cannot be selected.
- Every evaluated requirement records advertised value, satisfaction and a stable explanation suitable for UI/API diagnostics.
- Added a small provider-neutral constraint grammar: exact strings plus equality/inequality and ordered numeric dotted versions, with comma-separated conjunctions.
- Provider-specific version/channel semantics remain adapter responsibilities and do not enter `studio_core`.
- Adapted the design from `sdp-studio` capability validation and runtime probing while explicitly separating pure compatibility from adapter I/O.
- Added unit/adversarial tests covering canonicalization, duplicates, strict and compatible semantics, missing capabilities/values, unavailable profiles, ranking/tie-break behavior, all supported operators and invalid constraint syntax.
- Updated `PROJECTS_AND_EXECUTION.md`, backlog and ADRs to make the resolver boundary normative.

Validation/publication evidence is recorded after the pull-request CI and final `main` workflow complete; no result is claimed green before GitHub Actions reports it.

## 2026-09-02 — E1 portable operator contracts

Objective: reuse the mature `sdp-studio` operator semantics while establishing a smaller, immutable and engine-neutral Ronin contract before codegen, plugin discovery or runtime execution depend on it.

Implemented on validation branch `automation/operator-contracts`:

- Added immutable `OperatorPort`, `OperatorParameter`, `OperatorContract`, `OperatorCatalog` and `OperatorViolation` domain types.
- Operator versions are explicit through `OperatorRef`; catalogs canonicalize ordering and reject duplicate references.
- Contracts describe logical ports, semantic parameter kinds, batch/stream modes and required/forbidden capability names without engine/provider branches.
- Added deterministic node-to-contract validation for missing contracts, missing/invalid parameters, undeclared parameters, missing/duplicate/undeclared ports and unsupported port modes.
- Added a deliberately small portable seed catalog adapted from proven `sdp-studio` source/transform/quality/output semantics; plugin discovery, compiler hooks, previews and UI widgets stay outside `studio_core`.
- Added a golden snapshot for seed operator IDs/categories/versions plus adversarial tests for canonicalization, version selection, metadata validity, parameter typing, port validation and vendor-neutral catalog output.
- Retained the 100% line/branch coverage requirement; test diagnostics exposed and corrected both an incorrect expected violation count and unexercised domain behavior rather than lowering the threshold.
- Temporary diagnostic workflows were used only on the validation branch to obtain exact Ruff/mypy/pytest evidence where Actions logs were not directly exposed, and are removed from the publication candidate.

Validation history:

1. Ruff format and lint failures were corrected using the repository-pinned formatter/linter without weakening rules.
2. Strict mypy exposed an over-broad `object` annotation in metadata canonicalization; it was replaced with explicit `OperatorPort`/`OperatorParameter` typing.
3. The official `python -m pytest` command then exposed one test expectation error and 99.53% coverage; the expectation was corrected and unreachable/dead branching was removed while adding evidence for the `any` parameter kind.
4. Final PR and post-publication workflow evidence must be recorded only after those Actions complete successfully.

## 2026-09-02 — E1 portable diagnostic contracts

Objective: adapt the mature `sdp-studio` diagnostic semantics into safe deterministic Ronin domain contracts while keeping runtime/provider parsing outside the pure core.

Implemented on validation branch `automation/diagnostic-contracts`:

- Added immutable `DiagnosticPredicate`, `DiagnosticRule`, `DiagnosticFact`, `DiagnosticFinding` and canonical `DiagnosticCatalog` contracts.
- Replaced YAML-defined regular expressions with a bounded non-executable predicate grammar (`equals`, `contains`, `prefix`) over normalized category/code/message/source facts.
- Matching uses deterministic AND semantics and returns stable immutable findings carrying checks, remediation, documentation keys and normalized source evidence.
- Raw Spark, Kubernetes, Databricks, Fabric and future provider errors are intentionally adapter concerns; the core contains no provider parser or vendor-specific rule branch.
- Added a portable seed catalog adapted from proven `sdp-studio` failure categories: unresolved fields, type mismatch, resource exhaustion, unsupported capabilities, execution-mode mismatch, missing dependencies, access denial and shared-state mutation.
- Added golden/adversarial tests for metadata bounds, unsafe/invalid matcher input, canonical ordering, duplicate rejection, all matcher operations, case sensitivity, actionable findings and vendor-neutral seed output.
- Explicit finding ordering uses string-only keys so optional remediation/documentation metadata never creates runtime-dependent comparison failures.

Validation/publication evidence will be recorded only after pull-request CI and the final `main` workflow complete successfully; no gate result is claimed in advance.

Next E1 priority after this increment: portable `.ronin/` project configuration with deterministic serialization and machine-specific checkout/auth state kept outside committed project intent.

## 2026-09-02 — E1 portable project manifest

Objective: make project Git/runtime intent cloneable and deterministic without committing machine-specific authentication or checkout state.

Implemented on validation branch `feat/portable-project-manifest`:

- Added neutral repository `adapter_id` and explicit `manual` / `fetch` / `fast-forward` synchronization policy to `RepositoryBinding`.
- Added immutable `ProjectManifest` with canonical path `.ronin/project.json` and exact schema identifier `ronin.project/v1`.
- Added deterministic JSON serialization/deserialization for project identity, primary/supporting repositories, default refs/subdirectories/sync policy, opaque runtime profile references, capability requirements and resolution policy.
- `ProjectManifest.from_project()` strips workspace `auth_ref` values; committed intent never contains resolved credentials, connection bindings, tokens or local checkout paths.
- V1 deserialization rejects missing/unknown keys and malformed nested shapes rather than silently discarding future or corrupt intent.
- Kept filesystem I/O, atomic persistence, provider auth resolution and on-disk migration outside `studio_core`; the design reuses `sdp-studio` versioned metadata ideas without copying its Pydantic/YAML/provider-specific persistence boundary.
- Added adversarial tests for schema/key drift, malformed mappings/sequences, invalid repository/execution values, auth exclusion, deterministic ordering and capability-only execution.
- Updated `PROJECTS_AND_EXECUTION.md`, backlog and ADR-AUTO-010 to make the portable/project-workspace boundary normative.

Validation history so far:

1. The first PR run passed the dedicated negative architecture gate and stopped at Ruff format, proving formatting remained enforced before later checks.
2. The repository-pinned Ruff 0.16.5 formatter was applied on a temporary branch-only helper workflow; the helper was removed immediately after committing canonical formatting.
3. Full authoritative PR and post-publication `main` evidence is recorded only after all required jobs complete successfully; no green result is claimed in advance.

Next E1 priority after this increment: formalize stable `instance_key` allocation at authoring/import boundaries and extend identity properties for symmetric/structurally identical graphs.

## 2026-09-02 — E1 stable instance identity

Objective: make node identity reproducible across authoring, import, serialization and replay, including symmetric graphs with semantically identical nodes, without clocks, randomness or topology-dependent tie-breakers in the pure core.

Implemented on validation branch `feat/stable-instance-key-allocation`:

- Added immutable `InstanceAnchor` provenance for bounded `authoring` and `import` boundaries.
- Added deterministic `allocate_instance_keys()`; duplicate anchors are rejected instead of silently disambiguated by insertion order, graph traversal, clocks or process state.
- Persisted `instance_key` in canonical node serialization so identity evidence survives round trips.
- Deserialization now reconstructs canonical node semantics, re-derives `NodeId`, and rejects any serialized ID/key/semantic mismatch.
- Added golden identity vectors plus adversarial tests for malformed anchors, duplicate provenance, tampered identity evidence and missing persisted keys.
- Added a symmetric-graph property proving two identical transforms with distinct stable anchors remain distinct while reversed node/edge insertion order canonicalizes identically.
- Kept label changes outside identity while preserving labels as normal serialized presentation metadata.
- Added `docs/product/IR_IDENTITY.md` and ADR-AUTO-011 to make the authoring/import provenance boundary normative.
- Reused the proven `sdp-studio` concept that document IDs are allocated before lowering and carried through source provenance; its wall-clock/random ULID allocator is intentionally not copied into `studio_core`.
- `ronin-old` was inspected for notebook identity behavior but does not contain a reusable graph identity mechanism for this slice.

Validation history:

1. The first PR run passed format, lint, strict mypy, architecture contracts and `gates-negative`, then exposed two test-contract errors: an existing direct `Node` fixture lacked the newly required key, and the new symmetry test incorrectly expected a renamed serialized label to disappear.
2. Those tests were corrected without changing the identity design or weakening gates.
3. Exact-head PR run `33675180034` then completed successfully for `quality` and `gates-negative`; Format, Lint, Types, Architecture contracts and Tests all passed, including the enforced 100% line/branch coverage threshold.
4. This progress-log commit is followed by another authoritative exact-head PR CI pass before publication; post-`main` evidence is only claimed after the published SHA is verified.

Next E1 priority after this increment: introduce mutation testing for `studio_core` and establish a target threshold without reducing the existing 100% line/branch coverage gate.

## 2026-09-03 — E1 mutation-quality gate

Objective: add independent semantic test-strength evidence for `studio_core` while preserving the existing zero-exclusion 100% line/branch coverage gate.

Implemented on validation branch `feat/mutation-gate` / PR #10:

- Pinned `mutmut==3.7.0` in development dependencies and configured mutation only for `studio_core`.
- Added a strict repository gate requiring at least 90% killed mutants. Only killed mutants count positively; `no_tests`, suspicious outcomes, timeouts, interrupted checks and segfaults invalidate the evidence and fail the gate.
- Kept all production code free of mutation exclusions and `pragma: no mutate` escapes.
- Added an isolated mutation job to CI. A temporary `src -> python` alias accommodates mutmut's generated-mutant layout without changing Ronin's package structure.
- Cleared pytest's global coverage addopts only inside mutation execution so mutants are killed by behavioral assertions rather than coverage-plugin side effects. The normal `quality` job continues to run all tests and enforce 100% line/branch coverage.
- Added short-lived mutation evidence artifacts containing exported counts and the exact survivor list, making failures auditable even when Actions log transport is truncated.
- Added deterministic complete snapshots of the provider-neutral built-in operator and diagnostic catalogs plus exact metadata boundary tests. These are product regression contracts, not mutation-tool-specific production exceptions.
- Reuse searches across `sdp-studio` and `ronin-old` did not surface existing mutation-testing machinery suitable for adoption.

Validation history retained because it demonstrates active gates rather than a weakened path to green:

1. The first mutation configuration exposed both Ruff formatting drift and a mutmut copied-test import problem; the mutation selection was narrowed to pure-domain test suites while normal CI remained unchanged.
2. Attempts to wrap mutmut through Python subprocesses were rejected by repository security lint rules S607/S603; no lint suppression was added. An in-process Click wrapper also proved unreliable and was removed.
3. Splitting mutation execution, evidence export and score enforcement isolated the real blocker: mutation execution/export succeeded while the strict score failed.
4. Exact baseline evidence from run `33717248317` on `bbecf5056b1adb26e2805be3e0e5f541ce8ecfe3` was 1,599 killed, 508 survived, 2,107 total = 75.89%, with zero invalid categories.
5. Rather than lowering 90%, complete portable catalog snapshots and boundary assertions were added. A semantically correct but Ruff-unformatted test revision already achieved 1,899 killed / 208 survived / 2,107 total = 90.13%.
6. The formatted exact head `0cc7a4470e7c1bb472b90b0b098b631202f39b49`, run `33717624489`, completed `quality`, `mutation` and `gates-negative` successfully together. `quality` includes the mandatory 100% line/branch coverage gate; mutation evidence is exactly 1,899 killed, 208 survived, 2,107 total = 90.13%, with all invalid-evidence categories zero.
7. Documentation commits following that validated product/test head require a final authoritative exact-head PR CI pass before merge. Post-`main` evidence is recorded only after the published SHA is verified.

Next E1 priority after this increment: notebook cells and deterministic dependency analysis, followed by adapter-side runtime discovery and resolved-runtime execution snapshots.
