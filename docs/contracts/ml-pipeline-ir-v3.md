# Machine Learning Studio PipelineIR v3

PipelineIR v3 extends the durable local ML runner with statically registered
built-in stages and namespaced plugin stage declarations. PipelineIR v1 and v2
payloads and their validation semantics remain unchanged. V3 never loads plugin
Python code, imports or shell commands into the host process.

## Canonical shape

The top-level object retains `schema`, `nodes`, and `parameters`. `schema` is
`ronin.ml-pipeline-ir/v3`; parameters are string pairs bound by the API to the
current Lab's digest, task, backend, and seed, plus the digest of the built-in
and installed plugin stage registries (ports, config fields, executor IDs, effects, and checkpoint
codec identities). This digest also binds host executor and stage-validation source hashes, Python
implementation/version, and relevant numerical dependency versions. Algorithm and preprocessor choices belong in v3 stage
config. Each node has exactly these fields:

```json
{
  "id": "train-a",
  "kind": "train",
  "stage_version": 1,
  "config": {"algorithm": "logistic_regression"},
  "inputs": {"prepared": ["prepare-a.out"]}
}
```

Input references use `node_id.output_port`. References and input ports are
sorted in canonical JSON. Each current built-in stage exposes one `out` port;
the registry declares the output type and each consumer's accepted input type
and cardinality. The static immutable registry also pins the config validator,
effect class, checkpoint codec identity, and executor identity for each stage
version.

| Stage | Input ports and types | Output type | Effect |
| --- | --- | --- | --- |
| `profile` | none | `quality.profile` | pure |
| `quality_gate` | `profile`: one `quality.profile` | `quality.passed` | pure |
| `prepare` | `quality`: one `quality.passed` | `ml.prepared` | pure |
| `train` | `prepared`: one `ml.prepared` | `ml.model` | pure |
| `evaluate` | `model`: one `ml.model` | `ml.metrics` | pure |
| `select` | `candidates`: 1–23 `ml.metrics` | `ml.selected` | pure |
| `register` | `selected`: one `ml.selected` | `ml.selected` | registry write |

A graph has one `profile`, one `quality_gate`, and one `select`, with at most
one terminal `register`. It may contain multiple prepare/train/evaluate
branches; every computation must contribute to selection. Type checks reject
invalid ports, incompatible references, missing nodes, and incorrect
cardinality before a durable Job is created. The runner checks the Lab-specific
algorithm, preprocessor, clustering, and selection metric constraints at the
same boundary.

The built-in `quality_gate` accepts an optional `config.suite` containing a
`ronin.ml-quality-suite/v1` value. The API can compile a standard execution
with this suite into v3; its versioned rules are part of the pipeline digest.
The gate records per-expectation outcomes in its durable checkpoint and stops
before preparation/training when a `failure` expectation fails. See the
[quality suite contract](ml-quality-suite-v1.md) for supported rules and
severity behavior.

## Bounds and identity

V3 keeps the 24-node limit and stable serial topological execution. It also
caps the graph at 48 edges, each node's fan-out at eight, aggregate stage config
at 16 KiB, and the canonical payload at 64 KiB. Node IDs and registration
identifiers are at most 256 characters, and the bound parameter map contains at
most six unique string pairs. Cycles and orphan computation
are rejected. Stage version and typed references are part of the canonical
pipeline digest pinned to the Job. A checkpoint is reusable only when the
pipeline/runtime and upstream-output fingerprints match; changing the pinned
graph therefore cannot reuse stale outputs. The stage version pins its
checkpoint codec version as well. Node checkpoints larger than 256 KiB are
externalized to the ArtifactStore, with a 128 MiB hard ceiling; this allows a
valid 64 MiB model artifact plus its bounded JSON envelope to survive restart.

Selective retry accepts a bare stage kind to invalidate every matching stage
and its descendants. A node-specific retry uses `node:<id>` so IDs that collide
with built-in stage names remain unambiguous; the UI always uses this form.

`register` is a terminal host-managed side effect. It runs only after selected
artifact materialization, under the existing artifact writer lease, and keeps
the current idempotent conflict rules. Plugin stages use namespaced declarations
from the frozen contribution registry and execute in pinned, networkless OCI
containers with bounded canonical JSON, read-only root filesystems and resource
limits. Stage output is data-only JSON; plugin evaluators can return a `scores`
object as `ml.metrics`, bound to one direct model input. `artifact:read` exposes
only artifacts referenced by upstream pipeline nodes. `artifact:write` accepts
up to eight outputs and 512 KiB per stage. The host verifies these bytes and
persists artifact references with the node checkpoint under the shared writer
lease. Durable Job inventory discovers the references whether the checkpoint
is inline or stored as a separate checkpoint artifact.

The plugin declaration pins `distribution_digest` to the host-measured digest of
the installed distribution. Composition compares that value with the installed
package before freezing the stage registry; the digest is included in the
registry identity pinned to the Job.

The OCI process receives a canonical JSON request on stdin containing the
stage identity, config, typed inputs, and authorized upstream artifact bytes
encoded as base64. It returns strict UTF-8 JSON
`{"output":{...},"artifacts":[...]}` on stdout; host redaction is disabled
for this bounded data channel and stderr is discarded so diagnostics cannot
corrupt the protocol. Each
artifact has a unique bounded name, media type, and base64 data. The whole
request and response are each capped at 1 MiB. Model inputs above 512 KiB are
rejected before base64 encoding, and host-side request encoding counts bytes
incrementally. For `ml.metrics`,
`output.scores` is a non-empty map of metric names to finite numbers.
