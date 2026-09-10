# Ronin portable evidence reference v1

Status: **alpha public contract for v0.1 construction**.

## Public representation

Authenticated `GET /v1/jobs/{job_id}/evidence`, `ronin evidence JOB_ID`, and `pyronin` expose the same storage-neutral v1 fields:

- `version`: integer `1`;
- `cell_id`: canonical cell identity when evidence belongs to one cell, otherwise `null`;
- `role`: stable logical role;
- `availability`: `available`, `missing`, `tombstoned`, or `unavailable`;
- `digest_algorithm`: `sha256` when trustworthy identity exists, otherwise `null` only for `unavailable`;
- `digest`: lowercase SHA-256 when trustworthy identity exists, otherwise `null` only for `unavailable`;
- `media_type`: media type when known, otherwise `null`;
- `size_bytes`: non-negative verified byte length when trustworthy identity exists, otherwise `null` only for `unavailable`;
- `reason`: bounded normalized reason only for `unavailable`, otherwise `null`.

Physical `storage_ref` / locator data is deliberately absent from the public representation. Backend paths, buckets, URIs and provider handles are never canonical evidence identity.

## Logical identity and availability

Logical content identity is `(role, digest_algorithm, digest, media_type, size_bytes)`. Availability and physical location are state around that identity, not part of it.

`available` requires trustworthy content identity and a private physical locator at the storage adapter. Consumers must verify bytes against the digest before reuse. `missing` means identity is known but the expected content cannot currently be resolved. `tombstoned` means retention intentionally removed physical content while preserving its recorded identity. Both `missing` and `tombstoned` therefore retain digest and size but carry no locator.

`unavailable` means no trustworthy identity was produced. It must omit digest algorithm, digest, size and locator and must carry an explicit bounded reason. Ronin never fabricates zero size, placeholder digests or provider locators to represent absence.

## Durable storage

SQLite schema version 3 migrates the former digest-keyed evidence table to an evidence-record key that can represent records without a digest. Existing schema-2 evidence migrates losslessly as `available`. Closed availability values and identity/state consistency are enforced both by the domain object and SQLite CHECK constraints.

The in-memory and SQLite adapters consume the same `StoredEvidenceRef` contract. Worker writes remain lease-fenced. Both adapters enforce a hard v0.1 maximum of 100 evidence references per Run. Non-available records cannot be converted back into executable `ExecutionEvidenceReference` values, so they cannot become reusable execution evidence accidentally.

## Serialization and evolution

Canonical v1 wire serialization is UTF-8 JSON. Producers emit `version: 1`; consumers reject unsupported versions and unknown availability values. The current alpha clients intentionally validate the complete field set while #54 owns the broader additive-field/evolution policy.

Kernel roles are `log`, `metric`, `trace`, `lineage`, `output`, `resource`, and `cost`; durable internal artifacts may use additional documented roles such as `cell-result`. Provider-specific resource syntax or storage metadata does not enter this contract.

## Public path and bounds

The public route resolves `job_id` to the latest logical Run and reads through `DurableExecutionService` and `BoundedAsyncJobStore`; it does not call the synchronous store directly from the HTTP thread. Authentication and normalized 400/401/404/503 behavior follow the existing job-control surface.

Evidence retrieval is a single v0.1 collection rather than a separately paginated resource. The durable adapters reject a 101st reference rather than truncating output, and transport clients retain the existing 1 MiB response bound. A future contract that needs larger collections must introduce explicit keyset pagination rather than silently widening or truncating this boundary.

## CLI and SDK

`ronin evidence JOB_ID` prints one line per reference; `--json` emits each public v1 object without adding storage metadata. The official Python SDK exposes `EvidenceReference`, `EvidenceAvailability`, `Ronin.get_evidence(job_id)`, and `JobHandle.evidence()` using the same field and availability semantics.

## Dirty Git patch evidence

A dirty Git revision may optionally link to a redacted patch artifact in addition to the existing dirty digest. That artifact is **deferred for v0.1** rather than required by this public evidence slice. The existing dirty-state digest remains canonical execution identity; no raw dirty patch content is persisted merely to satisfy this contract.

If a patch artifact is introduced later, it must use this content identity contract, pass secret/redaction policy, and never expose credentials, ignored secret files, path escapes, or backend-specific identity.

## Qualification status

This implementation makes the frozen step-12 capability present in supported code paths, but the repository is currently in maintainer-directed code-only mode. GitHub Actions and automated tests are disabled, so the last automated acceptance baseline remains **13/15** with gaps `01` and `12`. Do not describe step 12 as automatically qualified until automated validation is explicitly restored and executed.
