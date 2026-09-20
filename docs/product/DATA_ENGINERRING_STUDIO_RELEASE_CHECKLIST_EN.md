# Data Enginerring Studio — Release Checklist

## Local quality gate

From `repo-analysis`:

```powershell
$files = Get-ChildItem tests -Filter 'test_data_engineering_*.py' |
  ForEach-Object { $_.FullName }
pytest -q @files
ruff check python/studio_data_engineering tools/data_engineering_qualification.py
python -m compileall -q python/studio_data_engineering
```

All tests must pass, Ruff must be clean, and bytecode compilation must finish.

## HTTP and UI gate

```powershell
pytest -q tests/test_studio_static.py tests/test_data_engineering_ui.py tests/integration/test_data_engineering_http.py
```

The same-origin E2E must verify Studio HTML, health, validation, preview, and
durable run planning. The browser qualification runner is:

```powershell
$env:PYTHONPATH = 'python;tests/integration'
python tools/run_data_engineering_browser_e2e.py
```

## Spark Connect and SDP Studio gate

Configure an imported SDP Studio project and run:

```powershell
$env:SDP_PROJECT_ID = '<imported-project-id>'
$env:SDPSTUDIO_DATA_ROOT = '<isolated-sdp-data-root>'
pwsh tools/run_data_engineering_external_e2e.ps1 -SparkHome '<path-to-site-packages\\pyspark>'
```

The runner starts the official Spark Connect server, executes the Spark smoke,
persists evidence, and runs the official `sdpstudio validate` command. The
expected SDP output is `Pipeline model is valid.`.

The JSON-stdio adapter test can additionally be run with
`SDP_STUDIO_COMMAND`; it is optional and does not replace the official CLI
gate.

## Durable execution gate

Verify that:

1. `/v1/data-engineering/health` reports `status=ready`.
2. Local preview produces an artifact and `StoredEvidenceRef`.
3. The outbox is marked published only after successful delivery.
4. A stale lease token cannot write evidence.
5. Observed lineage preserves `execution_ref` and exports OpenLineage data.

## Release decision

The module is release-ready only when every mandatory gate passes and the
configured Spark/SDP external run has no skipped mandatory tests. If an
external provider is unavailable, report
`implementation-ready / external-validation-pending`; do not report a fully
operational release.
