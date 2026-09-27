# ML Pipeline IR Contract v1

Canonical identifier: `ronin.ml-pipeline-ir/v1`.

The intermediate representation is a deterministic directed acyclic graph. Each
node has a stable `node_id`, `kind`, and JSON-serializable `config`; edges are
represented by node input references. Node IDs are unique and execution order
is the stable topological order, with lexical `node_id` tie-breaking.

The initial runtime supports the tabular training path and treats the lab's
feature/target definition as the executable minimum. Future nodes may add
select, impute, encode, split, train, evaluate, and register operations. A
consumer must fail closed on cycles, unknown required node kinds, missing input
references, or duplicate output names.

IR is data, not executable code: configs must contain primitives, arrays, and
objects only; callables, imports, shell commands, and arbitrary code are
invalid. The serialized envelope is `{schema, lab_id, lab_version, nodes}`.
Changing node semantics requires a new schema version or an explicit node
version; old IR must remain replayable for provenance.
