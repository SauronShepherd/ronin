# Ronin v1 API compatibility contract

Status: **alpha contract for v0.1 construction**.

This document defines compatibility semantics for the supported `/v1` HTTP surface, the installed Ronin CLI client, the version-controlled OpenAPI 3.1 document, and the independent `pyronin` package. It does not make transport, `http.server`, SDK classes, or any framework type part of the canonical execution/storage domain.

## Current compatibility stage

Ronin is currently **alpha** (`0.1.0a*`). Alpha uses a deliberately strict, fail-closed protocol policy so undocumented server/OpenAPI/CLI/SDK drift is not silently accepted as a compatibility promise.

For the current alpha stage:

- response objects are **closed**: every documented field is required when OpenAPI marks it required, and unknown top-level fields are rejected by supported clients;
- request objects are closed unless a schema explicitly allows extension data (`SubmitJobRequest.parameters` is the current intentional open object);
- closed semantic enums such as job state and evidence availability reject unknown values;
- error **codes** are an open string vocabulary inside one fixed error envelope, so a new code can be surfaced without teaching clients a false meaning;
- cursor values are opaque to clients and versioned privately by the server; malformed, mismatched, unsupported-version, over-limit, or filter-incompatible cursors fail closed;
- incompatible alpha protocol changes require a coordinated server/OpenAPI/CLI/SDK release. A path remaining `/v1` is not permission to drift one component independently.

## Public object shapes

The current response shapes are exactly those in `api/openapi-v1.json`:

- `Job`: `id`, `state`, `failure_code`;
- `JobPage`: `items`, `next_cursor`;
- `JobEvent`: `sequence`, `attempt_id`, `attempt_sequence`, `kind`, `message`, `occurred_at`;
- `JobEventPage`: `items`, `next_since`;
- `JobEvidence`: `items`;
- `EvidenceReference`: `version`, `cell_id`, `role`, `digest_algorithm`, `digest`, `media_type`, `size_bytes`, `availability`, `reason`;
- `Error`: exactly one `error` object containing exactly `code` and `message`.

`failure_code`, evidence availability, and evidence identity rules remain domain-specific contracts; this document only defines compatibility behavior around their wire representation.

## Error contract

Every Ronin HTTP error response uses:

```json
{"error":{"code":"job_not_found","message":"job does not exist"}}
```

The envelope and the `error.code` / `error.message` fields are closed alpha shape. `code` is a non-empty bounded string and `message` is a non-empty bounded human-readable string. Supported clients must not accept legacy top-level `code` or infer a code from free-form text.

Known server codes currently include `unauthorized`, `invalid_request`, `invalid_job_id`, `not_found`, `job_not_found`, `idempotency_conflict`, and `storage_backpressure`. The value space is intentionally open: a future code may be surfaced as an unknown string while its HTTP status remains authoritative. Clients must not treat an unknown error code as success.

Malformed/non-Ronin error bodies are not interpreted as canonical Ronin errors. SDK/CLI clients report the HTTP failure with a generic protocol-envelope message instead of manufacturing a code.

Bearer credentials are never included in public error bodies, CLI formatting, or SDK exception messages.

## Canonical instants

Public `Instant` values use exactly UTC RFC3339-style text with six fractional digits:

`YYYY-MM-DDTHH:MM:SS.ffffffZ`

The OpenAPI `Instant` pattern, server-emitted `Instant` values, CLI parser, and SDK parser must agree. Merely receiving a non-empty string is not sufficient.

## Cursor compatibility

`cursor` and `since` are opaque bounded strings. Clients may store and replay them but must not decode, modify, concatenate, or derive identity from them.

Alpha server cursor encoding is private and versioned. An unsupported cursor version, a cursor for another Run/filter, malformed encoding, or a value beyond the published byte bound is rejected rather than interpreted heuristically. During alpha an incompatible server release may invalidate older cursors; this must be called out in release notes. Beta/stable promotion requires a declared cross-version cursor support window before this rule can be relaxed.

## Enum and state evolution

`JobState` and `EvidenceAvailability` are closed semantic enums because clients perform control-flow decisions from them. Adding a new value is therefore a coordinated protocol change during alpha; older typed clients fail closed instead of mapping an unknown value to an existing state.

Error-code values are different: they identify failure detail under an already authoritative HTTP error status and are intentionally open. New error codes do not become success states and do not alter lifecycle semantics.

## Stage promotion rules

### Alpha

Current rule: closed response shapes, closed semantic enums, open error-code values, opaque versioned cursors, coordinated releases for any incompatible shape change. No deprecation window is promised.

### Beta

Before a beta release, Ronin must explicitly decide whether response objects become additive-tolerant. If so, OpenAPI `additionalProperties`, CLI parsing, SDK parsing, fixtures, and release notes must change together. Required-request additions, removals/renames, type changes, and closed-enum additions remain breaking unless a versioned migration is defined. Cursor support windows must be documented.

### Stable

Before stable v1, incompatible removals/renames/type changes or required-request additions require a new versioned surface or a documented deprecation/migration window. Optional additive response fields may only be considered compatible if the beta policy and all supported clients already tolerate them. Closed-enum evolution and cursor support guarantees must be explicit rather than inferred.

## Request validation

`POST /v1/jobs` accepts only `project`, `target`, and optional `parameters`; unknown request fields are rejected. `parameters` is intentionally extensible JSON object data and is not interpreted as protocol field expansion.

Known query parameter sets are closed per route. Limits remain `1..100`. Public `job_id` values are bounded by the canonical lifecycle ID contract. The server must not silently discard unknown query or request fields.

## OpenAPI / CLI / SDK synchronization

`api/openapi-v1.json` is the wire schema authority for the public v1 surface. `SUPPORTED_ROUTES` in `studio_server` must not contain an undocumented public route, and OpenAPI must not advertise an unimplemented route. CLI/SDK response parsers must implement the same required fields, closed object shapes, cursor bounds, canonical instant format, error envelope, and closed enum values.

While maintainer-directed code-only mode is active, these guarantees are validated by static source/schema review only. GitHub Actions and automated tests are intentionally disabled and no runtime conformance evidence is claimed. When automated qualification is restored, server/OpenAPI/CLI/SDK drift checks and real HTTP contract cases must be reinstated without weakening this contract merely to make qualification pass.

## Current v0.1 boundary

The supported endpoint set remains frozen to submit/list/status/events/evidence/cancel. This compatibility slice does not add endpoints, framework dependencies, OIDC, enterprise RBAC, provider-specific identity, or new execution capabilities. Scoped HTTP authorization is separately owned by #161 and must consume the existing typed-grant model without redefining this wire compatibility policy.
