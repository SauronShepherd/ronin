# Ronin portable evidence reference v1

Status: **alpha contract for v0.1 construction**. This document defines the storage-neutral identity consumed by durable execution and the public `/evidence` representation.

## Schema

A portable evidence reference has these fields:

- `version`: integer `1`.
- `role`: stable logical role. Kernel execution roles are `log`, `metric`, `trace`, `lineage`, `output`, `resource`, and `cost`; durable internal artifacts may use additional documented roles such as `cell-result`.
- `digest_algorithm`: `sha256` in v1 when trustworthy content identity exists, otherwise `null` only for `unavailable`.
- `digest`: 64 lowercase hexadecimal SHA-256 characters when trustworthy content identity exists, otherwise `null` only for `unavailable`.
- `media_type`: media type when known, otherwise `null`.
- `size_bytes`: non-negative byte length when trustworthy content identity exists, otherwise `null` only for `unavailable`.
- `locator`: optional physical storage locator. A locator is not part of logical content identity and may change when content moves. **The public job evidence API does not expose this field.**
- `availability`: `available`, `missing`, `tombstoned`, or `unavailable`.
- `reason`: normalized reason required only for `unavailable`; `null` otherwise.

Logical identity is `(role, digest_algorithm, digest, media_type, size_bytes)`. `locator`, Run/cell ownership, availability and backend-specific metadata are excluded. Identical bytes with the same logical role and media type therefore retain the same identity across storage backends.

For `available`, digest and size are required and consumers must verify bytes before trusting or reusing content. A digest mismatch fails closed. `missing` means the referenced content was expected but cannot currently be resolved and retains its last trustworthy logical identity. `tombstoned` means retention policy intentionally removed the physical content while preserving its recorded logical identity. `unavailable` means no trustworthy content identity or locator was produced; implementations must carry an explicit reason at their boundary and must not fabricate zero size, a fake digest, or a provider locator.

## Serialization and extensions

Canonical v1 wire serialization is UTF-8 JSON with object member names from this schema. Producers must emit `version: 1`; consumers must reject unsupported major versions. Unknown top-level fields are reserved for additive alpha evolution and may be ignored only when they do not alter the meaning of required v1 fields. Unknown values for `availability`, `digest_algorithm`, or a required kernel `role` fail closed. Duplicate JSON member names must be rejected by any future canonical parser before mapping to this contract.

Available runner evidence is represented by `ExecutionEvidenceReference.portable_payload()`. Durable storage wraps the same logical values in `StoredEvidenceRef` and additionally carries all four availability states. Run/cell ownership is context, not part of artifact content identity. Public serialization is produced from that durable model and deliberately omits `storage_ref`/`locator`.

## Storage and retention

Physical storage schemes such as `artifact://`, local filesystem paths, S3 URIs, OCI references, or another backend belong to adapters. Canonical identity never requires a provider name, bucket, registry, engine, telemetry vendor, or cloud IAM identifier.

Moving verified content between stores may replace only the locator. Deleting content under an intentional retention policy changes availability to `tombstoned`; an unexpected resolution failure is `missing`. Neither state is reusable execution evidence until bytes are available and digest-verified again. An `unavailable` durable row persists null digest algorithm, digest, size and locator; the backing SQL representation therefore never invents content identity merely to satisfy a storage key.

## Dirty Git patch evidence

A dirty Git revision may optionally link to a redacted patch artifact in addition to the existing dirty digest. If emitted, the patch uses this same content identity contract, a documented patch media type, and a safe adapter locator. Patch bytes must pass the existing secret/redaction policy before persistence. The Git dirty digest remains the execution identity; the optional patch artifact is explanatory evidence and must not introduce credentials, ignored secret files, path escapes, or a backend-specific identifier into canonical VCS identity.

## Current v0.1 implementation boundary

The local Docker worker composition uses a portable wrapper around the existing file-fsynced execution evidence store. It preserves the local `local-evidence://` locator internally but computes SHA-256, media type, and exact byte size over the persisted canonical JSON. The content-addressed artifact store independently uses SHA-256 and verifies bytes on read. Conformance fixtures require identical canonical bytes written through these two local storage paths to retain the same digest and size even though their locators differ, and corrupted artifact bytes fail verification.

Durable worker checkpoints persist each runner-produced portable evidence reference as a first-class `StoredEvidenceRef`, correlated to the canonical Run and cell, before the cell checkpoint advances. The stored cell-result JSON carries the same portable payload instead of reducing evidence to `kind` plus a physical locator. Opaque legacy runner evidence fails closed at the durable worker boundary and is not checkpointed.

The public control-plane surface now maps Job -> latest Run -> durable evidence through the storage-neutral execution service. `GET /v1/jobs/{job_id}/evidence`, `ronin evidence`, OpenAPI and `pyronin` use the same availability vocabulary and portable identity. No public response exposes the local storage locator. The frozen real-Docker acceptance journey requires both `log` and `resource` references for each of six actually executed demo cells.

Legacy opaque `ExecutionEvidenceReference(kind, ref)` values remain constructible during alpha migration for non-durable integrations, but `StoredEvidenceRef.from_execution_reference()` rejects them. Durable/public available evidence must carry portable content identity.

## Remaining #53 work

- Decide and implement the safe optional dirty-patch artifact link when Git evidence is promoted through D1; do not store raw dirty content without redaction/secret qualification.
- Keep availability transitions and retention behavior storage-neutral as storage consolidation proceeds under the release hardening plan.

The public evidence contract itself is now bound across durable storage, HTTP, CLI, OpenAPI and SDK. #53 should remain open until the optional dirty-patch requirement is explicitly completed or removed by decision; #54 may be advanced only to the extent its API/SDK evidence acceptance is satisfied.
