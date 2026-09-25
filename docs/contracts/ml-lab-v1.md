# ML Lab Contract v1

Canonical identifier: `ronin.ml-lab/v1`.

An ML Lab is the immutable-at-execution definition of a tabular experiment. Its
persisted identity is `lab_id` plus a monotonically increasing `version`; an
execution must reference both values so that changing a draft cannot alter a
running experiment.

Required fields:

- `name`: non-empty human-readable label.
- `task`: `classification` or `regression`.
- `features`: ordered array of `{name, role}`; role is currently `feature`.
- `target`: non-empty source column name and must not be listed as a feature.
- `backend_id`: adapter identity, for example `local.sklearn`.
- `dataset_ref`: logical dataset/artifact reference, never an embedded dataset.

Optional fields include `description`, `tags`, `test_fraction` (strictly between
0 and 1), `random_seed` (non-negative integer), and algorithm parameters.
Unknown fields must be preserved by storage when possible and ignored by v1
execution; this permits forward-compatible UI metadata without changing the
training contract.

Compatibility rule: v1 consumers must reject an unsupported `task`, missing
identity, duplicate feature names, target/feature collision, or invalid split.
Adding optional fields is backward compatible; changing field meaning requires
`ronin.ml-lab/v2` and a migration.
