# Ronin portable evidence reference v1

Status: **alpha contract for v0.1 construction**. This document defines the storage-neutral identity that must be consumed by durable execution and the future `/evidence` representation before that public endpoint ships.

## Schema

A portable available evidence reference has these fields:

- `version`: integer `1`.
- `role`: stable logical role. Kernel execution roles are `log`, `metric`, `trace`, `lineage`, `output`, `resource`, and `cost`; durable internal artifacts may use additional documented roles such as `cell-result`.
- `digest_algorithm`: `sha256` in v1.
- `digest`: 64 lowercase hexadecimal SHA-256 characters.
- `media_type`: media type when known, otherwise `null`.
- `size_bytes`: non-negative byte length when content is available and verified.
- `locator`: optional physical storage locator. A locator is not part of logical content identity and may change when content moves.
- `availability`: `available`, `missing`, `tombstoned`, or `unavailable`.

Logical identity is `(role, digest_algorithm, digest, media_type, size_bytes)`. `locator` and backend-specific metadata are excluded. Identical bytes with the same logical role and media type therefore retain the same identity across storage backends.

For `available`, digest and size are required and consumers must verify bytes before trusting or reusing content. A digest mismatch fails closed. `missing` means the referenced content was expected but cannot currently be resolved. `tombstoned` means retention policy intentionally removed the physical content while preserving its recorded logical identity. `unavailable` means no trustworthy content identity or locator was produced; implementations must carry an explicit reason at their boundary and must not fabricate zero size, a fake digest, or a provider locator.

## Serialization and extensions

Canonical v1 wire serialization is UTF-8 JSON with object member names from this schema. Producers must emit `version: 1`; consumers must reject unsupported major versions. Unknown top-level fields are reserved for additive alpha evolution and may be ignored only when they do not alter the meaning of required v1 fields. Unknown values for `availability`, `digest_algorithm`, or a required kernel `role` fail closed. Duplicate JSON member names must be rejected by any future canonical parser before mapping to this contract.

The current Python domain object exposes the same required fields through `ExecutionEvidenceReference.portable_payload()`. Durable storage wraps the same logical values in `StoredEvidenceRef`; Run/cell ownership is context, not part of artifact content identity.

## Storage and retention

Physical storage schemes such as `artifact://`, local filesystem paths, S3 URIs, OCI references, or another backend belong to adapters. Canonical identity never requires a provider name, bucket, registry, engine, telemetry vendor, or cloud IAM identifier.

Moving verified content between stores may replace only the locator. Deleting content under an intentional retention policy changes availability to `tombstoned`; an unexpected resolution failure is `missing`. Neither state is reusable execution evidence until bytes are available and digest-verified again.

## Dirty Git patch evidence

A dirty Git revision may optionally link to a redacted patch artifact in addition to the existing dirty digest. If emitted, the patch uses this same content identity contract, a documented patch media type, and a safe adapter locator. Patch bytes must pass the existing secret/redaction policy before persistence. The Git dirty digest remains the execution identity; the optional patch artifact is explanatory evidence and must not introduce credentials, ignored secret files, path escapes, or a backend-specific identifier into canonical VCS identity.

## Current v0.1 implementation boundary

The local Docker worker composition uses a portable wrapper around the existing file-fsynced execution evidence store. It preserves the local `local-evidence://` locator but computes SHA-256, media type, and exact byte size over the persisted canonical JSON. The content-addressed artifact store independently uses SHA-256 and verifies bytes on read. Conformance fixtures require identical canonical bytes written through these two local storage paths to retain the same digest and size even though their locators differ, and corrupted artifact bytes fail verification.

Legacy opaque `ExecutionEvidenceReference(kind, ref)` values remain constructible during alpha migration for non-durable integrations, but `StoredEvidenceRef.from_execution_reference()` rejects them. Durable/public evidence must carry portable content identity before `/evidence` is exposed.

## Remaining #53 work before public `/evidence`

- Persist runner-produced log/resource references as first-class durable `JobStore` evidence rather than only preserving their locators inside the cell-result payload.
- Carry explicit missing/tombstoned/unavailable representation through durable persistence and the public API shape.
- Decide and implement the safe optional dirty-patch artifact link when Git evidence is promoted through D1; do not store raw dirty content without redaction/secret qualification.
- Bind the future OpenAPI/SDK evidence representation directly to this contract and add real server/SDK conformance before closing #53/#54.
