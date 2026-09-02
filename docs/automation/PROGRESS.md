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
