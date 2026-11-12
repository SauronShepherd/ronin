# Phase receipt — full Python regression after QueryFlux CAS hardening — 2026-11-12

## Candidate

- Source: `195fa66a9cedd81528b14f27e276682138e36008`
- Command: `python -m pytest -q`
- Environment: Windows, Python 3.13

## Result

```text
4532 passed, 77 skipped in 622.74s (0:10:22)
```

The skipped cases are explicit environment-gated lanes for real Docker,
PostgreSQL, Trino, OTLP, S3/Azurite, Spark/SDP and host-specific symlink/POSIX
capabilities. No test failed and no skip was converted into a pass claim.

## Decision

PASS for the full Python regression gate after QueryFlux lifecycle
serialization. This receipt does not qualify the planned asynchronous
QueryFlux worker, provider conformance, public cancel routes, or any external
service lane. Public v1 remains **0/13 (0%) — NO-GO**.
