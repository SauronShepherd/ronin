# HTTP JSON ingestion contract

`http.json` is a bounded, provider-neutral read connector. A connection stores
only non-secret options and `secret_refs`; bearer material is resolved at read
time and is never included in definitions, checkpoints, logs, or evidence.

## Safety defaults

- `base_url` must use HTTPS unless `allow_http=true` is explicitly selected.
- DNS and literal IP targets that are private, loopback, link-local, reserved,
  multicast, or unspecified are rejected unless the local profile sets
  `allow_private_network=true`.
- Redirects are disabled. A redirect is not an implicit trust boundary.
- Responses must be JSON and are bounded by `max_response_bytes` (default
  10 MiB, maximum 100 MiB) and the caller's `limit` (maximum 100,000 rows).
- Every resolved record must be an object with a consistent field shape.

## Pagination and reliability

Pagination is opt-in and always bounded:

- `page_param` adds a one-based query parameter (`page=1`, `page=2`, ...).
- `page_size` controls the expected page size and cannot exceed the read limit.
- `next_url_field` follows an absolute HTTP(S) URL in an object response;
  relative or non-HTTP URLs fail closed.
- `max_pages` defaults to one and is capped at 1,000.
- `max_retries` defaults to zero and is capped at ten. HTTP 429 and 5xx
  responses, timeouts, and network errors use exponential backoff.
- `retry-after` is honored for throttled/server responses and capped at 60
  seconds per attempt.
- `rate_limit_seconds` inserts a deterministic delay between pages.

The snapshot checkpoint is the SHA-256 digest of the concatenated response
bodies in page order. Re-reading the same snapshot returns no rows, while a
changed page sequence produces a new checkpoint. Checkpoints are therefore
advanced only after the governed reader has obtained the complete bounded
response sequence.

The connector's local qualification is in
`tests/test_connector_registry.py`; it exercises a transient 503, retry,
two-page read, row limit, and deterministic request order.
