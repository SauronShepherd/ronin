# Performance Studio

`ronin-plugin-performance` is the community Performance Studio plugin for Ronin. It
is deliberately engine-neutral: adapters can normalize Spark event logs,
MadMamba runtime/bundle records, and MadLava JSONL snapshots into
`ronin.performance-run/v1`. The analyzer then produces deterministic findings
and chart-ready series without inventing missing measurements.

The initial rule set covers task skew, shuffle pressure, memory/disk spill, and
small-file pressure. Findings include severity, numeric evidence, and a
concrete remediation. The plugin declares `performance.analysis`,
`performance.visualizations`, and `performance.recommendations`, contributes
the isolated `performance.analyze` job, exposes `POST
/api/v1/performance/analyze`, and provides a declarative UI surface. Job and
HTTP entry points call the same application service.

The intended next adapters are:

1. Spark event-log reader: `SparkListener` stage/task metrics, executor and SQL
   plan metadata, with support for rolling logs and history-server replay. The
   first normalizer is available as `normalize_spark_events`.
2. MadMamba reader: bounded runtime lifecycle, process/IO samples, and bundle
   records, preserving its fail-open/degraded semantics. The first normalizer
   is available as `normalize_madmamba_records`.
3. MadLava reader: method profiling, Spark serialization boundaries, runtime
   identity, and report sequence/dropped-snapshot metadata. The first
   normalizer is available as `normalize_madlava_snapshots`.
4. Correlation layer: asset lineage and runtime spans, cost attribution,
   regressions against prior runs, and anomaly baselines.

Thresholds are intentionally explainable and should become versioned policy
configuration rather than hidden heuristics before a 1.0 release.
