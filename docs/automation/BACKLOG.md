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

## E1 — Core IR

Completed in the first slice:

- Immutable `NodeId`, `Port`, `Node`, `Edge` and `Pipeline` primitives.
- Canonical node/edge ordering independent of insertion order.
- Stable semantic node identity using semantic content plus an explicit stable instance key; labels do not affect identity.
- Canonical JSON serialization/deserialization with deterministic round-trip behavior.
- Edge validation for unknown nodes, exact ports, batch/stream compatibility, schema compatibility and cycles.
- Hypothesis properties for deterministic identity and canonical insertion order.
- Adversarial deserialization tests and randomized test ordering.
- 100% line/branch coverage gate for `studio_core` from the first meaningful domain implementation.

Next:

1. Adapt the mature `sdp-studio` operator and diagnostics catalogs into provider-neutral Ronin contracts with golden tests.
2. Formalize stable `instance_key` allocation at authoring/import boundaries and extend identity properties for symmetric/structurally identical graphs.
3. Introduce mutation testing for `studio_core` and reach the target threshold without reducing coverage.
4. Add notebook cells and dependency analysis only after operator/diagnostic contracts are stable.

## Later reuse

- Reuse/adapt `sdp-studio` codegen, source maps, runners, debug, collaboration, auth/scheduling, React/XYFlow/Monaco and deployment work behind Ronin boundaries.
- Selectively reuse `ronin-old` native execution/Gluten/Velox and hardened redaction/session ideas; do not revive its monolithic API/controller architecture.

## Security carry-over

The historical Fakebrick review contains P0/P1 findings (control-plane isolation, secrets, pod recreation, authorization and JWT validation). They remain requirements for E2, but none should be marked fixed until corresponding runtime code exists in this repository and regression tests prove the property.
