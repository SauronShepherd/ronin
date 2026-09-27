# Performance Studio architecture

Performance Studio is a community Ronin plugin (`com.sauronshepherd.ronin.performance`).
It owns performance findings, policies, reports and UI contributions; it does
not own job execution, asset catalog metadata, lineage storage or runtime
instrumentation. Those systems provide evidence through public ports.

## Evidence flow

```text
Spark event log ─┐
MadMamba bundle ─┼─> normalizer ─> ronin.performance-run/v1
MadLava JSONL ───┘                         │
                                          ├─> analyzer: findings + score + series
                                          ├─> correlation: explicit lineage rows
                                          ├─> regression: baseline comparison
                                          └─> renderer/UI: charts + recommendations
```

The normalizers do not fabricate metrics. Missing source measurements remain
missing. Every report records its effective `ronin.performance-policy/v1` so a
finding can be reproduced after thresholds change.

## Ronin integration

| Contribution | Contract |
|---|---|
| capability | `performance.analysis`, `performance.visualizations`, `performance.recommendations` |
| job | `performance.analyze` |
| HTTP | `POST /api/v1/performance/analyze` |
| permissions | `performance:read`, `performance:analyze` |
| isolation | `worker` |
| UI | Performance Studio routes and chart declarations |
| distribution | `ronin.plugins.v1` entry point, independent wheel |

Job and HTTP entry points call the same application service. The host only
knows the manifest and contributions; it does not import source-specific
adapters to discover the plugin.

## Source coverage

- Spark: completed stages, accumulables, shuffle read/write and memory/disk
  spill; task metrics can be attached by normalized producers.
- MadMamba: validated diagnostic bundle records and bounded runtime lifecycle
  evidence; fail-open/degraded state remains source evidence.
- MadLava: report snapshots, method profiling counts, runtime identity and
  Spark serialization sections; exact byte claims remain constrained by the
  source report's accuracy metadata.

## Safety and scale

Parsing is bounded by source bundle validation and capped renderer rows. The
plugin is isolated because event-log replay and future adapters may be
resource-intensive. Reports contain measurements and redacted metadata only;
they must not become a path for secrets or arbitrary payloads.

## Current status and planned extensions

1. Stage/task lineage adapters for full asset-to-method correlation.
2. Executor memory/GC and CPU saturation findings.
3. Streaming micro-batch latency, state-store growth and backpressure rules.
4. Cost attribution and anomaly baselines across retained runs.
5. Native Ronin UI entry (`#/performance`) is implemented and consumes the shared
   analysis API. Persistent report history and multi-run exploration remain future
   extensions.
