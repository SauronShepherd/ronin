# Data Enginerring Studio — Operations Runbook

## Startup checks

Confirm that the plugin and its workspace dependency are ready, and that
`/v1/data-engineering/health` returns `status=ready`. Verify the artifact and
compilation stores before allowing durable runs.

## Runtime configuration

`local-preview` requires no external service. `spark-connect` requires
`SPARK_CONNECT_ENDPOINT` in `sc://host:port` form. SDP execution requires an
imported SDP Studio project and an isolated `SDPSTUDIO_DATA_ROOT`.

Never treat a configured endpoint as proof of availability. Run the
qualification smoke and retain its output as release evidence.

## Incident handling

- Validation failures: preserve the IR digest and diagnostics; do not submit
  an invalid revision.
- Spark Connect failures: retain the provider endpoint and normalized error,
  then retry only through the durable run policy.
- SDP failures: preserve source artifacts and the source digest; do not replace
  the imported project with generated output.
- Evidence failures: inspect lease fencing and artifact-store health. A stale
  lease must remain unable to write.
- Outbox failures: retry delivery idempotently and preserve the event payload.

## Recovery and audit

Revisions and evidence are immutable. Recovery creates a new revision or run;
it must not overwrite a prior artifact. Use compilation records, outbox events,
execution references, and lineage observations to reconstruct an incident.
Keep Spark and SDP qualification output with the release record.

## Security

The browser is not an authorization boundary. All plugin routes are protected
by control-plane authentication and typed permissions. Do not place Spark, SDP,
or artifact-store credentials in pipeline JSON, browser storage, or evidence.
