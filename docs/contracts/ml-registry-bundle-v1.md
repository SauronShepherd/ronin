# ML Registry Bundle Contract v1

Canonical identifier: `ronin.ml-registry-bundle/v1`.

The ML registry bundle contains canonical JSON objects for experiments, feature
definitions, runs, evaluations and registered model versions. Feature
definitions are included only when a `FeatureDefinitionStore` is supplied;
evaluations are collected from the registry when supported. When an
`ArtifactStore` is supplied to export, every
referenced model artifact is copied into a `ml_artifact` inventory object using
the `ronin.ml-artifact/v1` payload. The payload carries the original storage
reference, SHA-256 digest, role, media type and base64 encoded bytes.

Export fails closed when a referenced artifact has no model digest metadata or
when the artifact store cannot verify and read the bytes. Import validates the
bundle manifest, object media types and every artifact digest before any registry
mutation. An import containing artifact objects requires a destination artifact
store; bytes are written content-addressably and model/run references are
remapped to the destination storage references before registry writes. SQLite
imports commit experiments, runs, model versions, evaluations and feature
definitions in one database transaction; exact replays are idempotent, while a
conflict rolls the metadata transaction back. Feature definitions require a
transaction-aware feature store on the same SQLite database and an existing
workspace-scoped catalog revision for each referenced dataset. Stores without
an atomic import adapter fail closed.

Artifact bytes are materialized before the SQLite metadata transaction because
the artifact store has a separate durability boundary. If metadata commit later
fails, content-addressed bytes may remain unreferenced; the import does not
publish partial registry metadata, and normal artifact retention can collect
unreferenced objects. PostgreSQL ML registry Bundle import remains unavailable
until its atomic adapter is implemented.

Metadata-only bundles remain supported for references intentionally managed by an
external artifact provider. They do not claim to be self-contained and must be
imported without artifact objects. Secrets and provider credentials are never
serialized into the bundle.

PostgreSQL compositions pass the shared `ArtifactReferenceBarrier` to the
import operation. Its writer lease covers destination artifact materialization,
reference remapping, and all registry/feature commits as one publication
window, so retention cannot observe a partially imported bundle. SQLite and
metadata-only imports may omit the barrier.
