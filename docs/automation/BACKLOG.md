# Autonomous build backlog

Items are ordered by the construction plan and by risk. Selection is always revalidated against the real repository state before implementation.

## E0 — Foundation

Completed:

- Executable pure-domain I/O boundary.
- Executable package dependency matrix for all planned `studio_*` layers.
- Dedicated negative-gate harness proving deliberate I/O, environment and layer violations fail.
- Ruff, strict mypy, pytest and CI baseline.

Next:

1. Add secret and dependency security gates (`gitleaks`, dependency audit) with negative fixtures where practical.
2. Add documentation contracts so status, architecture decisions and generated evidence cannot silently drift from the repository.
3. Establish governance files and a durable ADR structure before substantive domain code arrives.
4. Add manifest validation only when Kubernetes/Compose/Helm artifacts enter the repository; do not create placeholder infrastructure merely to satisfy a gate.
5. Add coverage and mutation gates when executable product behavior exists; do not create meaningless percentage targets over empty packages.
6. Evaluate augmenting the in-repo dependency gate with `import-linter` once multiple domain/adaptor packages exist. The current AST gate remains authoritative until an additional tool demonstrates equivalent or stronger coverage.

## E1 — Core IR

1. Implement immutable `NodeId`, `Port`, `Node`, `Edge` and `Pipeline` primitives with canonical ordering.
2. Add deterministic stable identifiers and serialization round-trip properties.
3. Introduce operator and diagnostics catalogs with golden tests.
4. Add notebook cells and dependency analysis only after core IR contracts are stable.

## Security carry-over

The historical Fakebrick review contains P0/P1 findings (control-plane isolation, secrets, pod recreation, authorization and JWT validation). They remain requirements for E2, but none should be marked fixed until corresponding runtime code exists in this repository and regression tests prove the property.
