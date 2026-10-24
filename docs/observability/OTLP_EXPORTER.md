# OTLP/HTTP exporter

Ronin can export normalized metrics, events, and spans to an OpenTelemetry
Collector over OTLP/HTTP. The exporter is optional and does not replace Ronin's
durable run, event, audit, or evidence stores.

## Configuration

Set the standard OTLP environment variables before constructing the exporter:

```powershell
$env:OTEL_EXPORTER_OTLP_ENDPOINT = 'http://127.0.0.1:4318'
$env:OTEL_EXPORTER_OTLP_HEADERS = 'Authorization=Bearer%20collector-token'
$env:OTEL_SERVICE_NAME = 'ronin'
$env:OTEL_RESOURCE_ATTRIBUTES = 'deployment.environment=dev'
```

```python
from studio_observability import OtlpHttpExporter

exporter = OtlpHttpExporter.from_environment()
```

The endpoint is a base URL. Ronin posts JSON to `/v1/traces`, `/v1/metrics`,
and `/v1/logs`. HTTPS is supported. URL credentials, query strings, and
fragments are rejected. Header values are held in memory for requests and are
never included in exporter logs or payloads.

### Local collector with Docker

The repository includes a development collector configuration at
`deploy/observability/otel-collector.yaml`. Start the pinned collector in one
PowerShell window:

```powershell
$collectorConfig = (Resolve-Path .\deploy\observability\otel-collector.yaml).Path
docker run --rm -p 127.0.0.1:4318:4318 `
  --mount "type=bind,source=$collectorConfig,target=/etc/otelcol/config.yaml,readonly" `
  otel/opentelemetry-collector-contrib:0.162.0 `
  --config=/etc/otelcol/config.yaml
```

Set `OTEL_EXPORTER_OTLP_ENDPOINT` to `http://127.0.0.1:4318` in the Ronin
process. The development configuration uses the Collector `debug` exporter so
accepted traces, metrics, and logs are visible in its output.

## Export and backpressure

Call `export_metrics`, `export_events`, or `export_spans` with a bounded batch.
Each call returns `True` when the batch entered the queue and `False` when the
exporter is closed or its queue is full. A full queue increments
`stats.backpressure_batches`; it does not block the caller or change job state.
Network and collector failures are counted in `stats.failed_batches` and do
not escape the worker into execution code. `flush(timeout_seconds)` waits for
accepted batches to finish, while `close(timeout_seconds)` stops the worker.

The defaults cap the queue at 64 batches, each batch at 256 records, and each
serialized payload at 256 KiB. These bounds can be lowered or raised through
the constructor, within the documented safety limits. Ronin metrics with
`kind="counter"` are emitted as monotonic OTLP delta sums; gauges remain gauges.

## Redaction

Attributes with names containing `authorization`, `password`, `secret`,
`token`, `credential`, `api_key`, or `private_key` have their values replaced
with `[REDACTED]`. Bearer strings and common `key=value` secret patterns are
redacted in text fields. Configured OTLP header values are also removed if they
appear in telemetry text. Applications should still keep arbitrary credentials
and personal data out of event messages; redaction cannot identify unknown
secret formats.

## Example

```python
from studio_observability import MetricPoint, OtlpHttpExporter
from studio_orchestrator import Instant

exporter = OtlpHttpExporter.from_environment()
try:
    accepted = exporter.export_metrics(
        (
            MetricPoint(
                "ronin.rows.processed",
                128.0,
                "rows",
                "counter",
                Instant("2026-10-24T00:00:00.000000Z"),
            ),
        )
    )
    if not accepted:
        # Count or surface this backpressure signal without failing the job.
        pass
    exporter.flush(timeout_seconds=2)
finally:
    exporter.close(timeout_seconds=2)
```
