# Canonical JSON identity v1

Ronin identity-bearing JSON uses the compatibility profile `ronin/canonical-json/v1`. This document freezes bytes that were previously produced independently by Python call sites; it does not silently redefine already-persisted identities.

## Canonical bytes

For a valid v1 payload, canonical bytes are UTF-8 JSON with object members ordered lexicographically by key, no insignificant whitespace, separators `,` and `:`, and non-ASCII Unicode emitted as UTF-8 rather than `\u` escapes when Python's encoder does not otherwise require escaping. Object keys are strings. Values are limited to JSON null, booleans, integers, finite floating-point numbers, strings, arrays, and objects recursively composed from those values.

Non-finite numbers (`NaN`, positive infinity, negative infinity, including an exponent that decodes to infinity) are invalid. Duplicate object members are invalid at canonical parsing boundaries. Unsupported Python objects and non-string object keys are invalid rather than stringified.

### Floating-point compatibility boundary

Existing v1 IR and public `SubmitJobRequest.parameters` accept finite floating-point values. Therefore this slice does **not** adopt a float-rejecting rule that would change already-valid v1 inputs or persisted checkpoint/request identities. The legacy v1 byte representation is preserved exactly by `studio_core.canonical_json.encode`; in particular negative zero is encoded exactly as `-0.0`.

This is a compatibility constraint, not a claim that Python's full finite-float rendering algorithm is a language-neutral numeric standard. New identity schemas should prefer integers or strings for quantities where cross-language equality matters. A future rule that rejects floats or changes their rendering requires an explicit identity/schema version boundary and migration; it cannot silently replace v1.

## Parsing boundary

`studio_core.canonical_json.decode` rejects duplicate object members and non-finite numbers before a payload is admitted to a canonical identity boundary. The public `POST /v1/jobs` request body now uses this parser before request/idempotency identity is computed, so duplicate members and non-finite values fail closed at the HTTP boundary as well. Presentation JSON and opaque storage cursors are intentionally outside this contract.

## Published vectors and independent checker

`tests/golden/canonical_json_v1.json` publishes exact canonical UTF-8 text and SHA-256 digests for ordering, Unicode, nesting, booleans/null, a large integer, legacy `-0.0`, persisted cell-resume identity, and the public HTTP request/idempotency identity shape. It also publishes required rejection inputs for duplicate members and non-finite numbers.

`tools/canonical_json_check.go` is a standard-library-only independent checker. It parses every published vector without Python, rejects duplicate members, preserves numeric lexemes with Go `json.Number`, recomputes canonical bytes and SHA-256 digests, and verifies the complete published vector set. The checker deliberately validates the published v1 byte contract; it does not claim an independent general algorithm for normalizing arbitrary finite IEEE-754 values beyond those exact lexical vectors.

## Current identity boundaries

The shared codec is the required boundary for identity-bearing or durable canonical JSON. Current covered surfaces include project manifests, notebook documents, IR, worker identity inputs, resume/cell execution identity, kernel/session events, and public HTTP request/idempotency identity. JSON used only for presentation and opaque cursor encoding remains intentionally outside the canonical identity contract.

## Versioning rule

Any change that alters canonical bytes for an input accepted by v1 is identity-breaking. Such a change requires a new explicit identity/schema version, migration rules for durable resume/idempotency state, updated goldens, and at least one independent checker. Existing v1 digests remain interpretable using this profile.
