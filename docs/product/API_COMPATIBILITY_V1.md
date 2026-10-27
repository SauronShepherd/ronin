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

- `Job`: `id`, `project_id`, `state`, `created_at`, `updated_at`, `failure_code`;
- `JobPage`: `items`, `next_cursor`;
- `JobEvent`: `sequence`, `attempt_id`, `attempt_sequence`, `kind`, `message`, `occurred_at`;
- `JobEventPage`: `items`, `next_since`;
- `JobEvidence`: `items`;
- `EvidenceReference`: `version`, `cell_id`, `role`, `digest_algorithm`, `digest`, `media_type`, `size_bytes`, `availability`, `reason`;
- `SqlResult`: `columns`, `rows`, returned by the optional read-only SQL service;
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

`POST /v1/sql` accepts `project`, `sql`, optional `parameters`, and optional
`max_rows` (`1..10000`), `timeout_ms` (`1..60000`, default `5000`), and
`max_result_bytes` (`1..10485760`, default `1048576`). Each binding may be a legacy JSON scalar or a tagged
`{"type": "integer", "value": 42}` object. Tagged parameter types are `null`,
`boolean`, signed 64-bit `integer`, finite `float`, and `string`; each object is
closed to exactly `type` and `value`. At most 1,000 parameters are accepted and
strings are bounded to 512 KiB. Legacy scalars remain supported for v1 clients and
are normalized using their JSON type. The request requires the project's `read` grant. The
reference DuckDB service accepts one read-only `SELECT` statement, bounds SQL text
to 1 MiB, and rejects mutating or multi-statement input. Deployments without a
configured SQL engine return `404 sql_unavailable`. SQL result rows use JSON-safe
scalars: UTC timestamps are RFC 3339 strings with `Z`, dates/times use ISO 8601,
decimals and UUID-like values are strings, and binary values are standard Base64
strings. Non-finite numeric results are rejected, and raw engine diagnostics are
never returned to clients.

The plugin route
`POST /v1/workspaces/{workspace_id}/projects/{project_id}/data-engineering/queryflux/execute`
binds execution to an existing project in the authorized workspace and accepts an
optional `parameters` array using the same tagged scalar forms and limits,
`max_rows` (`1..1000000`, default `1000`), and `max_result_bytes`
(`1..10485760`, default `1048576`). Its shared `QueryRequest` accepts only the
common read-only `SELECT` grammar and includes typed bindings and both output
budgets in its canonical request digest; the durable evidence artifact stores
that digest, not the bound values. The selected engine must explicitly
advertise `parameter_binding: true` or authorization fails before submission.
The Trino transport uses `EXECUTE IMMEDIATE ... USING`; string values are
UTF-8/base64 encoded before they are placed in SQL expressions. The execution
orchestrator rejects excess rows or a serialized `{columns, rows, row_count}`
result over `max_result_bytes`, returns no partial result, and attempts to
cancel a still-running query. The dynamically contributed route is described
in the static core OpenAPI contract; it remains unavailable when the optional
provider runtime is not composed.

`POST /v1/platform/connectors/discover` accepts optional `page_size` and opaque
`cursor` fields. Its response always contains `schema`, `items`, `count`,
`has_more`, and `next_cursor`; `source_version` is present only when supplied by
the provider. The default page size is at most 1,000 and the requested size may
not exceed the connector's advertised maximum. Cursors are bound to the
authorized workspace, connection reference, resolved connection identity, and
connector. A cursor from another source scope, an unsupported cursor version,
or an invalid provider continuation value fails closed. A connector that claims
discovery but cannot produce bounded pages is unavailable through this public
route rather than being allowed to materialize an unbounded response.

Built-in S3 and Azure Blob discovery advertise a 1,000-item provider page cap.
The legacy Python `discover()` convenience method also stops after at most 100
provider pages or 10,000 matching assets and fails with guidance to use paginated
discovery instead of returning a silently truncated inventory. This bounded
fallback is not a substitute for continuing the public cursor page by page.

Ingestion checkpoint storage keys preserve the legacy `workspace/identity`
form only when neither component contains `/`. If either component contains a
slash, the adapter derives a deterministic `ronin:v2` key from the structured
pair, so distinct workspace/identity pairs cannot alias. Existing slash-bearing
legacy checkpoints are not silently reused; incremental planning fails as
missing until an explicit migration or authorized remap is implemented.

The request body is parsed through the shared `ronin/canonical-json/v1` decoder before authorization-sensitive request handling and before idempotency identity is computed. Duplicate object members and non-finite JSON numbers are therefore rejected with `400 invalid_request` instead of being interpreted with implementation-specific last-wins or non-standard numeric semantics. This is an alpha validation tightening: payloads containing duplicate members or non-finite numbers that older code may have accepted are no longer valid. Canonical bytes and request digests for valid v1 inputs are unchanged.

Known query parameter sets are closed per route. For `GET /v1/jobs`, the supported query parameters are `project`, `state`, `limit` and opaque `cursor`; `project` and `state` are applied before pagination, and a returned `next_cursor` is valid only for the same filter scope. Limits remain `1..100`. Public `job_id` values are bounded by the canonical lifecycle ID contract. The server must not silently discard unknown query or request fields. Duplicate query parameters are rejected.

## OpenAPI / CLI / SDK synchronization

`api/openapi-v1.json` is the wire schema authority for the public v1 surface. `SUPPORTED_ROUTES` in `studio_server` must not contain an undocumented public route, and OpenAPI must not advertise an unimplemented route. CLI/SDK response parsers must implement the same required fields, closed object shapes, cursor bounds, canonical instant format, error envelope, and closed enum values.

These guarantees are validated by the exact-head workflow suite and by local HTTP contract tests. Server/OpenAPI/CLI/SDK drift checks and real HTTP contract cases remain mandatory; they must not be weakened merely to make qualification pass.

## Current v0.1 boundary

The supported endpoint set includes submit/list/status/events/evidence/cancel and
the optional read-only SQL endpoint. This compatibility slice does not add
framework dependencies, OIDC, enterprise RBAC, or provider-specific identity.
Scoped HTTP authorization must consume the existing typed-grant model without
redefining this wire compatibility policy.
