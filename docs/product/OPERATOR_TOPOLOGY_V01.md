# Operator topology contract v0.1

Status: **alpha contract for v0.1 construction**.

Ronin's pure pipeline model rejects an exact duplicate edge `(source, source_port, target, target_port)` before topological ordering. Canonical edge sorting does not make duplicate edges legal.

Operator-aware topology validation is provided by `studio_core.validate_operator_pipeline(pipeline, catalog)`. It remains provider-neutral: the validator depends only on the canonical `Pipeline` and `OperatorCatalog`, not on a runtime, runner or provider adapter.

For each declared target input:

- `cardinality="one", optional=false` requires exactly one incoming edge;
- `cardinality="one", optional=true` accepts zero or one incoming edge;
- `cardinality="many", optional=false` requires one or more incoming edges;
- `cardinality="many", optional=true` accepts zero or more incoming edges.

Exact duplicate edges are invalid regardless of cardinality. Existing port kind/schema compatibility and DAG/cycle checks remain unchanged.

Topology violations use stable operator-validation evidence codes:

- `RONIN-OP-008`: a `cardinality="one"` input has more than one incoming edge;
- `RONIN-OP-009`: a non-optional input has no incoming edge;
- `RONIN-OP-010`: an edge targets an input not declared by the operator contract.

This is an alpha validation tightening. Previously accepted graphs that relied on duplicate exact edges or violated declared input cardinality are now invalid. Serialization and identity bytes are unchanged for graphs that already satisfy these semantics.

Under the current maintainer-directed code-only policy this contract is implemented and source-reviewed only. No test/CI qualification is claimed until automated validation is restored.
