# Full Python regression — current candidate

**Date:** 2026-11-12  
**Candidate SHA:** `ad4cc65af0a7b25ef1e65503b6d9a23f185b017c`

## Gate

Command:

```text
python -m pytest -q
```

Result: **4547 passed, 80 skipped, 0 failed** in 287.15 seconds.

The skipped cases are explicit environment-gated lanes for Docker,
PostgreSQL, S3/Azurite, Trino, OTLP, Spark/provider credentials and Windows
symlink/POSIX privileges. They are recorded as skips and are not promoted to
passes by this receipt.

## Correction covered

The connection-session contract now verifies that `ronin.session` is persisted
by the same validated handler that updates the runtime API configuration. The
stale source-string assertion was updated to assert this atomic contract.

## Decision

Current Python regression gate: **PASS**. Real provider lanes and the complete
Public v1 family/release gates remain separate and open. Public v1 remains
**0/13 (0%) — NO-GO**.
