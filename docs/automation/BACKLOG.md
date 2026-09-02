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
- Canonical JSON serialization/deserialization with deterministic round-trip behavior.
- Edge validation for unknown nodes, exact ports, batch/stream compatibility, schema compatibility and cycles.
- Hypothesis properties, adversarial deserialization tests and 100% line/branch coverage for `studio_core`.
- Multi-project pure-domain contracts: `Project`, canonical `ProjectCollection`, primary/supporting Git repository bindings, secret/connection references, runtime profile references and provider-neutral capability requirements.
- Per-project execution intent supports exact adapter-owned runtime profiles and compatible capability-based resolution without vendor branches in the core.
- Provider-neutral `RuntimeProfile`/`RuntimeCatalog` advertisement snapshots and pure deterministic resolution with per-requirement compatibility evidence, required/preferred semantics, availability filtering and stable fallback ranking.
- Versioned provider-neutral operator contracts for ports, semantic parameters, modes and required/forbidden capabilities; deterministic `OperatorCatalog`, stable validation evidence and a portable seed catalog adapted from mature `sdp-studio` semantics with golden/adversarial tests.

Next:

1. Adapt the mature `sdp-studio` diagnostics catalog into a safe provider-neutral Ronin diagnostic contract/matcher with deterministic findings and golden tests; keep runtime/vendor normalization outside `studio_core`.
2. Define portable `.ronin/` project configuration and deterministic serialization for repository-independent project intent; keep machine-specific checkout/auth bindings outside committed config.
3. Formalize stable `instance_key` allocation at authoring/import boundaries and extend identity properties for symmetric/structurally identical graphs.
4. Introduce mutation testing for `studio_core` and reach the target threshold without reducing coverage.
5. Add notebook cells and dependency analysis only after operator/diagnostic contracts are stable.
6. Add an adapter-side runtime discovery SPI and resolved-runtime execution snapshot after the operator/diagnostic contract is stable; reuse `sdp-studio` probing behind that boundary rather than moving I/O into `studio_core`.

## Later reuse

- Reuse/adapt `sdp-studio` codegen, source maps, runners, debug, collaboration, auth/scheduling, React/XYFlow/Monaco and deployment work behind Ronin boundaries.
- Reuse `sdp-studio` runtime capability discovery and environment concepts behind the new neutral project/execution contracts rather than retaining vendor booleans in the core.
- Selectively reuse `ronin-old` native execution/Gluten/Velox and hardened redaction/session ideas; do not revive its monolithic API/controller architecture.

## Operational invariant

After every publication/deployment to `main`, inspect the GitHub Actions runs for that SHA. A builder execution is not complete while mandatory workflows are still running or failing. Fix regressions and republish/recheck until green; if the increment cannot safely be made green, revert it rather than weakening a gate.

## Security carry-over

The historical Fakebrick review contains P0/P1 findings (control-plane isolation, secrets, pod recreation, authorization and JWT validation). They remain requirements for E2, but none should be marked fixed until corresponding runtime code exists in this repository and regression tests prove the property.
