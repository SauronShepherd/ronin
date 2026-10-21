# ML Pipeline IR Contract v2

Canonical identifier: `ronin.ml-pipeline-ir/v2`.

## Serialized shape

The envelope retains the v1 fields: `schema`, `nodes`, and `parameters`.
`parameters` is a string-to-string object and includes the digest of the Lab
that the plan is compiled for. Every v2 node contains exactly `id`, `kind`,
`depends_on`, and `config`. `config` is a recursively immutable canonical JSON
object. V2 does not accept executable values, callables, imports, shell
commands, or arbitrary code. The envelope and node shapes are exact; v1
continues to serialize without `config`.

## Supported candidate DAG

The first v2 executor supports classification and regression candidate
selection. A graph contains one `profile`, one dependent `quality_gate`, one
dependent `prepare`, two to eight `train` nodes, one `evaluate` node per train
node, and one `select` node depending on every evaluate node. Each train node
depends directly on the shared prepare node. Each evaluate node depends on
exactly one train node. The graph must be acyclic, and every dependency must
resolve. Other graph shapes fail before training.

Train-node `config` accepts only `algorithm`, whose value must be supported by
the Lab task and selected backend. Select-node `config` accepts only `metric`
and `direction`. Classification supports `accuracy`; regression supports `r2`
and `mean_squared_error`. Direction is `maximize` or `minimize`; the compiler
defaults `mean_squared_error` to `minimize` and the other supported metrics to
`maximize`. Ties resolve by lexical train-node ID. No implicit selection based
on serialized node order is permitted.

The runner verifies the Lab digest, complete graph shape, task, algorithms,
backend capabilities, and selection policy before executing any node. Stable
topological ordering and checkpoint dependency fingerprints include the full
v2 graph and each node's outputs. Unsupported v2 shapes are rejected rather
than partially interpreted. Registration nodes, clustering, arbitrary stage
configuration, plugin-defined stages, and hyperparameter search remain outside
this contract.
