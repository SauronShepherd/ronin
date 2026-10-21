# ML Pipeline IR Contract v1

Canonical identifier: `ronin.ml-pipeline-ir/v1`.

## Serialized shape

The canonical JSON envelope has exactly three fields: `schema`, `nodes`, and
`parameters`. `schema` is the canonical identifier above. `parameters` is an
object whose keys and values are strings; the compiler uses it for the Lab
digest and pinned runtime choices. Lab identity is bound through the
`lab_digest` parameter rather than separate `lab_id` or `lab_version` fields.

Each node has exactly `id`, `kind`, and `depends_on`. `id` is a unique,
non-empty stable string. `kind` is one of `profile`, `quality_gate`, `prepare`,
`train`, `evaluate`, `select`, or `register`. `depends_on` is an array of
unique node IDs. The graph rejects self-dependencies, unresolved references,
duplicate IDs, and cycles. Canonical serialization round-trips through
`PipelineIR.from_json()`.

The v1 model has no per-node `config` field, separate edge list, input ports,
or output names. Node options are not executable payloads in this schema.
Callables, imports, shell commands, and arbitrary code are never accepted.

## Ordering and execution

`PipelineIR.execution_order()` returns a deterministic topological order,
breaking ties by lexical node ID. This is a graph serialization contract; it
does not mean every valid `PipelineIR` is executable by every runner.

The current local runner executes exactly one each of `profile`, `quality_gate`,
`prepare`, `train`, `evaluate`, and `select`, wired in that order. It rejects
`register` and other non-local compositions before training so a stored graph
cannot be silently ignored. A scheduler must pass the pinned PipelineIR through
unchanged, and the runner verifies that its `lab_digest` matches the submitted
Lab. Configurable candidate selection is defined by the v2 contract; v1 remains
unchanged and replayable.

Changing the serialized shape requires a new schema version. Old v1 payloads
remain replayable for provenance.
