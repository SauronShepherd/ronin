# ML Lab Contract v1

Canonical identifier: `ronin.ml-lab/v1`.

An ML Lab is an immutable-at-execution definition of a tabular experiment. The
canonical v1 payload uses `id`, `project_id`, `dataset` (`asset_id` plus
`version`), `target`, `task`, `features` (`column` plus `role`), `backend_id`,
`seed`, and `test_fraction`. The Lab's identity is its workspace-scoped `id`
and canonical SHA-256 `digest`; v1 Labs are create-only. A changed definition
uses a new `id`. Each execution pins the Lab digest and the dataset revision.

Required fields are `schema`, `id`, `name`, `project_id`, `dataset`, `target`,
`task`, `features`, `backend_id`, `seed`, and `test_fraction`:

- `schema`: `ronin.ml-lab/v1`.
- `id`: non-empty identifier unique in its workspace.
- `name`: non-empty human-readable label.
- `project_id`: non-empty project identifier.
- `task`: `classification`, `regression`, or `clustering`.
- `features`: non-empty ordered array of `{column, role}`; role is one of `auto`,
  `numeric`, `categorical`, `text`, `datetime`, or `ignored`.
- `target`: non-empty source column name for supervised tasks; `null` for
  clustering. A target must not be listed as a feature.
- `backend_id`: adapter identity, for example `local.sklearn`.
- `dataset`: a governed `AssetRef`, never an embedded dataset.
- `seed`: non-negative integer.
- `test_fraction`: finite number strictly between zero and one.

`test_fraction` is used by supervised training; clustering does not split
rows. Additional JSON fields (including UI metadata) are accepted, preserved
through serialization and persistence, and ignored by v1 execution. They are
included in the canonical digest so an immutable Lab cannot silently change.
Only JSON objects, arrays, strings, numbers, booleans, and null are accepted in
additional fields.

Compatibility rule: v1 consumers reject unsupported task/feature roles,
missing required fields, duplicate feature names, target/feature collision,
invalid `AssetRef`, and invalid `test_fraction`. New fields are backward
compatible because they are preserved but ignored by execution. Renaming a
field, changing its meaning, or weakening immutable create-only identity
requires `ronin.ml-lab/v2` and a migration. See
[`ADR-ML-LAB-V1.md`](../architecture/ADR-ML-LAB-V1.md) for the reconciliation
decision and golden contract fixtures.
