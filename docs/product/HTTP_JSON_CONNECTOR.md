# HTTP JSON ingestion contract

`http.json` is a bounded, provider-neutral read connector. A connection stores
only non-secret options and `secret_refs`; bearer material is resolved at read
time and is never included in definitions, checkpoints, logs, or evidence.

The local control-plane CLI exposes the same public connector contract:

```text
RONIN_CONTROL_PLANE_URL=http://127.0.0.1:8081 \
  ronin connectors capabilities
ronin connectors discover --connector-id http.json --connection-ref conn-1
ronin connectors preview --connector-id http.json \
  --connection-ref conn-1 --asset-ref conn-1::orders \
  --destination-ref local/orders --checkpoint-identity orders-v1 --mode snapshot
ronin connectors plan --connector-id http.json \
  --connection-ref conn-1 --asset-ref conn-1::orders \
  --destination-ref local/orders --checkpoint-identity orders-v1 --mode snapshot
ronin connectors checkpoint-health --checkpoint-identity orders-v1
ronin connectors sync-submit --workspace-id workspace-1 --project-id project-1 \
  --definition-file ./orders-sync.json --idempotency-key orders-run-001
ronin connectors sync-status --workspace-id workspace-1 --project-id project-1 \
  --job-id 01H...
ronin connectors sync-cancel --workspace-id workspace-1 --project-id project-1 \
  --job-id 01H...
```

`sync-submit` accepts a UTF-8 JSON object file no larger than 1 MiB and requires
an explicit idempotency key so a caller can safely retry after a lost response.
Durable submissions must identify governed catalog revisions for both ends of
the operation. The source catalog asset must carry these non-secret properties
that bind it to the physical connector source:

```json
{
  "ronin.connector_id": "http.json",
  "ronin.connection_ref": "conn-1",
  "ronin.asset_ref": "orders"
}
```

The definition includes `source_revision_ref` (`asset_id` and `version`) and
`destination_asset_id`; both catalog assets and the source revision must already
exist in the selected workspace. For example:

```json
{
  "id": "orders-sync",
  "connector_id": "http.json",
  "connection_ref": "conn-1",
  "asset_ref": "conn-1::orders",
  "destination_ref": "local/orders",
  "checkpoint_identity": "orders-v1",
  "mode": "snapshot",
  "source_revision_ref": {"asset_id": "source-orders", "version": "v3"},
  "destination_asset_id": "curated-orders"
}
```

The worker creates the destination revision from the committed output digest,
records an `observed` `write` lineage edge with the durable Run ID, and advances
the checkpoint in one SQLite or PostgreSQL transaction. The output artifact is
written first; if the metadata transaction fails, it remains an unreferenced
artifact eligible for retention cleanup and the checkpoint does not advance.
Status and cancellation require both workspace and project IDs; the server
checks them against the durable job before returning events/evidence or
requesting cancellation. A running `ronin worker` with matching storage must
process queued jobs.

Sync status also reports lineage for the latest successful Run. It filters
downstream edges by the governed source revision and Run ID, returns at most
100 edges with a truncation flag, and lets Ingestion Studio show evidence and
lineage in separate panels.

`RONIN_CONTROL_PLANE_URL` defaults to `http://127.0.0.1:8081`; the job API
continues to use `RONIN_URL` (default `http://127.0.0.1:8080`).

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
