# Performance Studio

Open-source Ronin plugin for performance intelligence across data assets and
runtime executions. It is released under the repository Apache-2.0 license and
is installable as an independent wheel.

## What it provides

- `performance.analyze` isolated job and `POST /api/v1/performance/analyze`.
- Spark event-log, MadMamba bundle, and MadLava snapshot normalizers.
- Explainable findings for task skew, shuffle pressure, spill, and small files.
- Correlation of explicit asset, stage, runtime, and method lineage.
- Baseline regression detection and versioned `PerformancePolicy` thresholds.
- Chart-ready series and a dependency-free accessible HTML renderer.
- Published `ui_manifest.json` and `config_schema.json` resources.
- A native Ronin web entry at `#/performance` with run analysis, charts and findings.

## Install and discover

```bash
python -m pip install ronin-plugin-performance
ronin plugins list
```

The wheel declares the `ronin.plugins.v1` entry point and depends only on the
public Ronin plugin contracts. Heavy parsing and instrumentation remain outside
the host process through the plugin's worker isolation declaration.

## Normalized input

Adapters return `ronin.performance-run/v1`. Metrics are never inferred when the
source does not provide them. The output includes the effective
`ronin.performance-policy/v1`, findings with numeric evidence, and chart-ready
stage series.

## Development

```bash
PYTHONPATH=python:packages/ronin-plugin-performance/src python -m pytest -q tests/test_performance_*.py
```

The release gate also installs the built wheel into an isolated target,
discovers the `ronin.plugins.v1` entry point, verifies `ui_manifest.json` is
packaged, and executes the CLI against a normalized run. This is the clean-room
proof that the plugin does not depend on its source checkout.
