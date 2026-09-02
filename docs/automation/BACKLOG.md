# Autonomous build backlog

Items are ordered by the construction plan and by risk. Selection is always revalidated against the real repository state before implementation.

## E0 — Foundation

1. Expand static gates toward the specification: import-linter, secrets/dependency scanning, manifest validation and documentation contracts.
2. Add a general gates-negative harness so every quality gate has a deliberate failing fixture.
3. Establish governance files and ADR structure before substantive domain code arrives.
4. Add coverage and mutation gates only when executable product code exists; do not create meaningless percentage targets over empty packages.

## E1 — Core IR

1. Implement immutable `NodeId`, `Port`, `Node`, `Edge` and `Pipeline` primitives with canonical ordering.
2. Add deterministic stable identifiers and serialization round-trip properties.
3. Introduce operator and diagnostics catalogs with golden tests.
4. Add notebook cells and dependency analysis only after core IR contracts are stable.

## Security carry-over

The historical Fakebrick review contains P0/P1 findings (control-plane isolation, secrets, pod recreation, authorization and JWT validation). They remain requirements for E2, but none should be marked fixed until corresponding runtime code exists in this repository and regression tests prove the property.
