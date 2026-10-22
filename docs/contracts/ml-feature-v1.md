# ML Feature Definition Contract v1

`ronin.ml-feature/v1` is an immutable, workspace-scoped feature definition.
Each version binds a feature set to one exact governed `AssetRef` dataset
revision, project identity, ordered feature columns/roles and a named
transformation policy. Versions are positive PostgreSQL-compatible integers and
must increase monotonically for a feature ID.

The control plane exposes list, publish and versioned get routes under
`/v1/ml-studio/features`. Publishing the same ID/version is idempotent only
when the canonical definition is identical; a different payload or a version
that does not advance is rejected. SQLite, PostgreSQL and in-memory stores use
the same immutable semantics, so training and inference can reference the same
dataset snapshot without silently changing the feature definition.
