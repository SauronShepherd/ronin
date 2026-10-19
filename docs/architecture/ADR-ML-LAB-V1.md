# ADR: reconcile the ML Lab v1 contract

- Status: accepted
- Date: 2026-10-19
- Scope: `ronin.ml-lab/v1`

## Context

The Lab contract text described versioned Lab IDs, classification/regression
only, `dataset_ref`, a required target, an open `(0, 1)` split fraction, and
preservable unknown fields. The implemented v1 value and stores instead use a
workspace-scoped create-only ID, `AssetRef`, clustering with no target, an
`(0, 0.5)` split limit, and reject all unknown fields. This divergence blocks
reliable serialization, persistence, API and execution compatibility.

## Decision

The canonical v1 wire shape is the one already stored and returned by the
released code: `schema`, `id`, `name`, `project_id`, `dataset`, `target`,
`task`, `features`, `backend_id`, `seed`, and `test_fraction`. A Lab is
immutable for a `(workspace_id, id)` pair. A new definition gets a new ID;
executions pin the canonical Lab digest. No synthetic Lab `version` field or
Lab version migration is introduced in v1.

V1 supports classification, regression, and clustering. Clustering requires a
null target. `test_fraction` is finite and strictly between zero and one;
supervised runners additionally reject a fraction/data-size combination that
cannot produce valid train and test sets. Clustering accepts the field for
wire-shape stability and ignores it during execution.

Unknown JSON fields are accepted and round-tripped as Lab metadata. The
execution code ignores them, while the canonical digest includes them. This
keeps persisted definitions lossless and prevents a same-ID metadata change
from being mistaken for the original immutable definition. Only canonical
JSON values are permitted.

## Consequences

- Existing Lab rows remain readable without a database migration; their
  serialized canonical fields are unchanged.
- The stricter-than-contract half-split ceiling is removed from Lab and
  supervised `TrainingSpec`; dataset feasibility remains checked at runtime.
- Future incompatible wire or mutability changes require `ronin.ml-lab/v2`.
- The canonical examples in `tests/fixtures/contracts/ml-lab-v1-*.json` are
  compatibility fixtures; parsers and SQLite persistence must preserve them.

## Verification

`tests/test_ml_domain.py`, `tests/test_ml_sqlite.py`,
`tests/test_ml_tabular_runtime.py`, `tests/integration/test_ml_studio_http.py`,
and OpenAPI snapshot validation cover the contract surface. PostgreSQL
round-trip remains covered by the existing Docker qualification suite.
