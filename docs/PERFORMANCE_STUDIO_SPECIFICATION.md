# Performance Studio Specification

**Status:** Implemented v0.1.0
**Product:** Performance Studio
**Distribution:** `ronin-plugin-performance`
**Plugin ID:** `com.sauronshepherd.ronin.performance`
**License:** Apache License 2.0, inherited from Ronin
**Runtime:** Python 3.11+
**Plugin API:** Ronin `1.0`

## 1. Purpose and scope

Performance Studio is an open-source Ronin plugin for explaining performance
behavior across data assets, distributed execution stages, and instrumented
runtimes. It converts evidence emitted by Spark, MadMamba and MadLava into a
common report that can be consumed by the Ronin API, job runtime, CLI and UI.

The module is designed to answer four operational questions:

1. Which stage, task, asset or runtime is responsible for observed latency or
   resource pressure?
2. Is the problem caused by skew, shuffle, spill, garbage collection, poor
   parallelism, or file layout?
3. Did the current execution regress against a known baseline?
4. What concrete remediation should an engineer try next?

The module is engine-neutral at its core. Spark-specific, Python-runtime and
JVM-runtime evidence enters through adapters and is normalized before analysis.
Performance Studio does not replace Spark UI, Spark History Server, MadMamba or
MadLava; it composes their evidence into a cross-runtime diagnostic surface.

## 2. Functional requirements

### 2.1 Analysis

The analyzer MUST:

- accept a normalized `ronin.performance-run/v1` mapping;
- preserve the run identifier when supplied;
- produce deterministic findings for identical input and policy;
- never invent a metric that is absent from the source evidence;
- include numeric evidence for every finding;
- include a remediation recommendation for every finding;
- produce a bounded score and chart-ready series;
- include the effective policy in the report.

The current implementation detects:

| Finding | Evidence | Default condition | Severity |
|---|---|---|---|
| `task-skew` | Per-task durations | Maximum task duration exceeds the configured ratio and minimum duration | High |
| `spill` | Memory/disk spill bytes | Any memory or disk spill is observed | Medium/high |
| `shuffle-pressure` | Shuffle read/write bytes and stage duration | Shuffle throughput exceeds the configured bytes/second threshold | Medium |
| `small-files` | Asset file count and total bytes | File count and average file size exceed the configured pressure thresholds | Medium |
| `gc-pressure` | Stage GC time and duration | GC consumes at least the configured fraction of stage time | Medium |
| `low-parallelism` | Task count and stage duration | One long-running task represents the stage | Medium |

### 2.2 Asset inventory

`inventory_asset(path)` provides a non-mutating local inventory for a file or
directory. It reports:

- asset identifier/path;
- file count;
- total bytes;
- average file size;
- minimum and maximum file size;
- traversal depth and file limits;
- whether the result was truncated.

The inventory is bounded by `max_files` and `max_depth`. A truncated inventory
is explicitly marked and MUST NOT be presented as complete.

### 2.3 Correlation

The correlation service accepts explicit relationships and emits
`ronin.performance-correlation/v1` rows. It correlates:

```text
asset -> stage -> runtime -> method
```

Lineage is only reported when identifiers are present in the input. The
correlator never guesses relationships from names or timing proximity.

### 2.4 Regression analysis

`compare_runs(current, baseline)` emits
`ronin.performance-regression/v1` and compares matching stage IDs. It reports:

- current and baseline run IDs;
- duration delta ratio;
- shuffle delta ratio;
- baseline/current duration values;
- the set of regressed stages;
- a boolean `has_regressions`.

Default regression thresholds are:

- duration increase: 20 percent;
- shuffle increase: 25 percent.

These thresholds are service parameters and are intentionally separate from
the finding policy.

### 2.5 Recommendations

The service returns best-practice records with an ID, title, activation
condition and evidence source. The current baseline recommendations cover:

- partition sizing from observed task and shuffle metrics;
- early filtering and projection before wide transformations;
- file compaction and avoidance of over-partitioned writes;
- bounded instrumentation and inspection of dropped runtime snapshots.

Recommendations are advisory. Performance Studio does not mutate jobs,
rewrites data, changes Spark configuration or compacts files automatically.

### 2.6 Rendering

`render_report(report)` produces a dependency-free accessible HTML fragment
containing:

- report title and score;
- baseline/regression summary when available;
- SVG stage-duration bars;
- shuffle and spill context per stage;
- an accessible tabular fallback;
- escaped labels and values;
- `figure`, `figcaption`, `title`, `aria-label`, `caption` and table scopes.

The renderer caps the number of visualized stages to keep output bounded.

### 2.7 CLI

The wheel installs the `performance-studio` command:

```bash
performance-studio RUN_JSON \
  --baseline BASELINE_JSON \
  --policy POLICY_JSON \
  --html REPORT.html
```

All optional arguments are optional. The command always prints the normalized
analysis report as JSON. When `--html` is supplied it writes the rendered
report to the requested path.

## 3. Ronin plugin integration

### 3.1 Manifest

The plugin declares:

```text
id:          com.sauronshepherd.ronin.performance
name:        Performance Studio
version:     0.1.0
plugin_api:  1.0
isolation:   worker
edition:     community
```

### 3.2 Capabilities

The plugin owns these capabilities:

- `performance.analysis`
- `performance.visualizations`
- `performance.recommendations`

### 3.3 Permissions

- `performance:read` — read reports, charts and recommendations.
- `performance:analyze` — submit analysis requests and execute the analysis
  job.

### 3.4 Contributions

| Contribution | Value |
|---|---|
| Job | `performance.analyze` |
| HTTP route | `POST /api/v1/performance/analyze` |
| UI entry | `ronin_plugin_performance/ui_manifest.json` |
| Configuration schema | `ronin.performance/config-v1` |
| Isolation | `worker` |

The job handler accepts the application payload directly. The HTTP route uses
an adapter that converts Ronin's invocation envelope (`body`, query and route
parameters) into the application service payload. Both paths execute the same
analysis service and therefore cannot drift into separate business logic.

### 3.5 UI manifest

The packaged UI manifest declares:

- product name: `Performance Studio`;
- UI API version `1.0`;
- `/performance` overview route;
- `/performance/runs/:runId` run route;
- overview, stage timeline, asset health, runtime health, regression and
  recommendations views;
- stage duration, shuffle/spill, asset file-size and runtime method-hotspot
  charts;
- high, medium and low finding severities.

The plugin loads and validates this resource during registration. The UI
contribution also publishes the actual packaged entry path.

## 4. Data contracts

### 4.1 Normalized run: `ronin.performance-run/v1`

Minimal shape:

```json
{
  "schema": "ronin.performance-run/v1",
  "run_id": "run-2026-001",
  "source": "spark-event-log",
  "assets": [
    {
      "id": "events",
      "file_count": 1200,
      "bytes": 838860800
    }
  ],
  "runtimes": [
    {
      "id": "madlava-driver",
      "runtime": "jvm",
      "version": "0.1.0"
    }
  ],
  "stages": [
    {
      "id": "stage-4",
      "duration_ms": 52000,
      "task_count": 64,
      "tasks": [{"duration_ms": 1200}],
      "shuffle_read_bytes": 100000000,
      "shuffle_write_bytes": 40000000,
      "spill_memory_bytes": 0,
      "spill_disk_bytes": 1048576,
      "gc_time_ms": 4000,
      "asset_ids": ["events"],
      "runtime_id": "madlava-driver",
      "method_ids": ["example.Job.transform"]
    }
  ]
}
```

All fields other than `schema` and the fields needed by a specific analysis are
optional. Missing measurements remain absent or zero according to the
normalizer's source semantics; consumers MUST inspect source coverage before
interpreting zero as a measured value.

### 4.2 Policy: `ronin.performance-policy/v1`

```json
{
  "schema": "ronin.performance-policy/v1",
  "skew_ratio": 1.75,
  "min_skew_task_ms": 1000,
  "shuffle_bytes_per_second": 10000000,
  "small_file_count": 100,
  "small_file_average_bytes": 134217728,
  "gc_ratio": 0.2,
  "min_tasks_per_stage": 2
}
```

Policy validation rejects unsupported schema versions and invalid thresholds.
The policy is serialized into every analysis report for reproducibility.

### 4.3 Analysis report

The report contains:

- `schema` and `run_id`;
- effective `policy`;
- bounded `score`;
- `issues` with code, severity, title, evidence and recommendation;
- `series.stages` for charts;
- `correlation` rows;
- optional `regression` result;
- `best_practices`.

### 4.4 Finding structure

```json
{
  "code": "spill",
  "severity": "high",
  "title": "Shuffle spill detected",
  "evidence": {
    "stage_id": "stage-4",
    "spill_disk_bytes": 1048576,
    "spill_memory_bytes": 0
  },
  "recommendation": "Reduce partition pressure, review executor memory, and tune partition sizing."
}
```

## 5. Source adapters

### 5.1 Spark event logs

`normalize_spark_events(events)` accepts Spark listener event objects without a
PySpark dependency. It currently reads:

- `SparkListenerStageCompleted` and normalized `stage.completed` events;
- stage IDs;
- stage duration when submission/completion timestamps are available;
- `Accumulables` represented either as a dictionary or Spark's list of
  `{Name, Value}` objects;
- remote/read shuffle bytes;
- shuffle write bytes;
- memory bytes spilled;
- disk bytes spilled;
- optional normalized task metrics.

The adapter emits source `spark-event-log` and does not require a live Spark
cluster.

### 5.2 MadMamba

`normalize_madmamba_records(records)` consumes records after they have been
validated by MadMamba's diagnostic bundle reader. It preserves bounded runtime
and monitoring duration evidence and emits source `madmamba-bundle`.

MadMamba's integrity guarantees remain upstream responsibilities. Performance
Studio does not bypass manifest, checksum, sequence or schema validation.

### 5.3 MadLava

`normalize_madlava_snapshots(lines)` accepts JSON objects or JSONL strings and
reads:

- snapshot sequence;
- snapshot duration in nanoseconds, converted to milliseconds;
- method profiling sections and method count;
- runtime report structure.

It emits source `madlava-jsonl`. Exact serialization byte claims remain subject
to MadLava's own accuracy and coverage metadata.

### 5.4 Adapter design rules

Adapters MUST:

- be dependency-light;
- preserve source identity;
- preserve explicit source limitations;
- avoid secret and arbitrary payload propagation;
- be deterministic for the same input;
- be bounded where input size is untrusted;
- emit the normalized contract rather than engine-specific output.

## 6. Architecture

```text
Spark event log ─┐
MadMamba bundle ─┼─> adapter ─> performance-run/v1 ─> application service
MadLava JSONL ───┘                                      │
                                                        ├─ analyzer
                                                        ├─ correlator
                                                        ├─ regression engine
                                                        ├─ best-practice engine
                                                        └─ renderer/UI
```

### 6.1 Ownership boundaries

Performance Studio owns:

- performance policies;
- normalized performance reports;
- findings and recommendations;
- performance chart projections;
- its UI and API contributions.

It does not own:

- job scheduling;
- executor lifecycle;
- asset catalog metadata;
- lineage persistence;
- Spark configuration mutation;
- MadMamba runtime lifecycle;
- MadLava bytecode instrumentation;
- data compaction or repair.

### 6.2 Isolation

The manifest declares `worker` isolation because event-log replay, filesystem
inventory and future instrumentation adapters may be CPU-, memory- or
I/O-intensive. The current pure-Python analysis core remains dependency-light;
the isolation boundary is a host execution policy and does not require the
plugin to embed a cluster engine.

### 6.3 Resource loading

Packaged resources are loaded through `importlib.resources`, not filesystem
relative paths. Registration validates:

- UI manifest object shape, product and UI API;
- configuration schema ID and object type.

This makes source checkout, wheel installation and clean-room behavior
equivalent.

## 7. Configuration schema

The packaged `config_schema.json` is a JSON Schema document with ID
`ronin.performance/config-v1`. Its top-level object currently accepts a
`policy` object with the versioned policy fields.

The schema rejects unknown top-level and policy properties. Runtime policy
construction performs additional semantic validation, including ratios,
positive thresholds and supported schema versions.

## 8. Security and privacy

Performance Studio follows Ronin's plugin security model:

- permissions are namespace-qualified and declared in the manifest;
- analysis route and read/navigation access use separate permissions;
- plugin code runs under declared worker isolation;
- filesystem inventory is read-only;
- traversal is bounded by file-count and depth limits;
- HTML labels are escaped;
- reports should contain measurements and redacted metadata, not secrets;
- adapters must not copy arbitrary source payloads into reports;
- no source adapter executes user-provided code;
- no automatic data mutation is performed.

Deployments should still apply Ronin's plugin lockfile, artifact hash, host
compatibility and authorization controls.

## 9. Operational behavior

### Success

A successful analysis returns a JSON report with `schema`, score, findings,
series, correlation, regression and recommendations. A run with no findings
returns a score of 100 and an empty issue list; this means no configured rule
was triggered, not that the run is mathematically optimal.

### Invalid input

Invalid request bodies, invalid policy versions, malformed JSON and missing
asset paths raise explicit errors. The HTTP adapter requires an object body.

### Partial evidence

Partial source evidence is valid. Reports should be interpreted together with
the adapter source and the fields actually present. No-data is not silently
converted into a positive performance claim.

### Truncated inventory

When an asset inventory reaches its file limit, the result sets `truncated` to
true. Callers should surface that condition in the UI and avoid treating
counts as authoritative totals.

## 10. Testing strategy

The current test suite covers:

- finding detection for skew, spill, shuffle, small files, GC and parallelism;
- Spark list/dictionary accumulator formats;
- MadMamba and MadLava normalizers;
- lineage correlation;
- baseline regression;
- policy serialization and validation;
- bounded asset inventory;
- HTML/SVG escaping and accessibility markers;
- CLI JSON and HTML output;
- plugin capabilities, permissions, UI, job and route contributions;
- runtime route invocation through `PluginHost`;
- packaged UI and config resource loading;
- plugin architecture compatibility tests;
- wheel discovery in a clean-room target.

Required quality gates:

```powershell
python -m ruff check packages/ronin-plugin-performance/src tests/test_performance_*.py
$env:PYTHONPATH = "python;packages/ronin-plugin-performance/src"
python -m pytest -q tests/test_performance_*.py
python -m pip wheel packages/ronin-plugin-performance --no-deps --wheel-dir build/performance-wheel
```

The clean-room gate installs the wheel into an isolated target and verifies:

1. `ronin.plugins.v1` discovery;
2. `ui_manifest.json` availability;
3. `config_schema.json` availability;
4. CLI execution against a normalized run;
5. HTML report generation.

## 11. Packaging

The package is built with setuptools and declares:

```toml
[project.entry-points."ronin.plugins.v1"]
performance = "ronin_plugin_performance.plugin:factory"

[project.scripts]
performance-studio = "ronin_plugin_performance.cli:main"
```

The wheel includes:

- Python package modules;
- `ui_manifest.json`;
- `config_schema.json`;
- plugin entry-point metadata;
- CLI entry-point metadata.

The package has no runtime dependencies beyond Python and the public Ronin
plugin contracts supplied by the host environment.

## 12. Performance considerations

- Analysis operates on normalized in-memory structures and does not start a
  Spark cluster.
- Renderer output caps stage rows.
- Asset inventory caps traversal.
- MadMamba input is expected to be validated and bounded before normalization.
- Source adapters avoid importing heavyweight engines.
- Worker isolation allows future replay and instrumentation work without
  requiring the host process to carry engine dependencies.

For very large event histories, production deployments should pre-aggregate or
stream source events into bounded normalized stage records before invoking the
analysis service.

## 13. Reference implementation layout

```text
packages/ronin-plugin-performance/
├── pyproject.toml
├── README.md
└── src/ronin_plugin_performance/
    ├── __init__.py
    ├── adapters.py       # Spark, MadMamba and MadLava normalizers
    ├── analyzer.py       # findings, score and chart series
    ├── assets.py         # bounded filesystem inventory
    ├── cli.py            # performance-studio command
    ├── correlation.py    # lineage and baseline regression
    ├── config_schema.json
    ├── plugin.py         # Ronin manifest and contributions
    ├── policy.py         # versioned thresholds
    ├── renderer.py       # accessible HTML/SVG output
    ├── resources.py      # packaged resource loading/validation
    ├── service.py        # shared job/API application service
    └── ui_manifest.json
```

## 14. Current limitations

The following are intentionally not claimed as implemented in v0.1.0:

- direct Spark History Server API integration;
- executor-level live polling;
- automatic OpenTelemetry export;
- automatic Spark configuration tuning;
- automatic file compaction;
- streaming state-store and backpressure rules;
- cost attribution from cloud billing APIs;
- persistent report storage owned by the plugin;
- a framework-specific frontend implementation beyond the declarative UI
  manifest and portable renderer.

The native Ronin web entry is implemented as a thin client over the shared API;
these remaining items are extension points, not silent behavior.

## 15. Roadmap

1. Add streaming micro-batch and state-store metrics.
2. Add executor CPU, heap, GC and disk saturation adapters.
3. Add full Spark task event aggregation and SQL-plan correlation.
4. Add persistent historical baselines and anomaly detection.
5. Add cost and resource-efficiency attribution.
6. Expand the native Ronin frontend with persisted history and multi-run panels.
7. Add compatibility matrices for Spark and MadLava versions.

## 16. Design principles

Performance Studio follows these principles:

1. Evidence before inference.
2. Explainable findings before opaque scores.
3. Shared application services across API, jobs and CLI.
4. Engine-neutral contracts with source-specific adapters.
5. Bounded parsing and rendering.
6. Explicit partial-data semantics.
7. Portable packaging and clean-room verification.
8. Read-only diagnostics by default.
9. Versioned policies and schemas.
10. Community plugin ownership without core coupling.
