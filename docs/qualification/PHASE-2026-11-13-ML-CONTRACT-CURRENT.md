# ML/MLOps local contract regression — current candidate

**Date:** 2026-11-13  
**Candidate SHA:** `464925737ba1cf9c889c7b2617a0c64203d108ef`

## Gate

Command:

```text
$files = (Get-ChildItem -LiteralPath tests -Filter 'test_ml*.py' | ForEach-Object { $_.FullName })
python -m pytest -q $files
```

Result: **296 passed, 0 failed** in 79.67 seconds.

This root-module contract lane covers local ML foundation, execution,
orchestration, registry, candidate hardening, API/HTTP, interchange and
artifact-related behavior selected by the `test_ml*.py` file set.

## Boundary

This is local deterministic contract evidence. It does not claim MLflow or
network serving, external model-provider certification, production S3 vendor
qualification or complete installed ML Studio family closure. Public v1
remains **0/13 (0%) — NO-GO**.
