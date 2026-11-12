# Phase receipt — classical ML contracts — 2026-11-12

## Candidate

- Source candidate before this receipt: `ed594ab645bac89c89b4a952c86754464f5f8db4`.

## Evidence

- Collection confirmed `294 tests collected` across all `tests/test_ml_*.py` modules.
- The complete selection was executed in two terminal groups because a single invocation exceeded the command observation limit:
  - alphabetically first group: `111 passed in 24.01s`;
  - second group: `183 passed in 30.82s`.
- Aggregate: **294/294 passed**, 0 failures.

The selection covers ML domain contracts, datasets, feature definitions, classical clustering and tabular models, gradient boosting, optimization, orchestration, execution/persistence stores, artifact/provenance/security, backend capabilities, HTTP transport, quality/drift, plugin APIs, runner/checkpoints, and tabular runtime behavior.

## Scope boundary

This receipt does not claim the opt-in PostgreSQL or S3 artifact integrations, external model providers, or the complete installed live ML Studio journey. Those remain separate candidate/provider gates.

## Result

PASS for the local classical ML contract/regression surface: **294/294**. P8 and Public V1 remain incomplete; official release-qualified progress remains `0/13 (0%)`.
