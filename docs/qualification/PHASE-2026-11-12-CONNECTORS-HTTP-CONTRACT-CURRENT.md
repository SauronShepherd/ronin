# P2 — Connector and ingestion contract qualification

**Date:** 2026-11-12  
**Candidate SHA:** `54c2e18fee22a66d1fb4adf61482e968ad1c1d79`

## Results

Contract and bounded provider-neutral regression:

```text
python -m pytest -q tests/test_connector_registry.py \
  tests/test_s3_json_connector.py tests/test_azure_blob_json_connector.py \
  tests/test_ingestion_sync.py
```

Result: **84 passed, 0 failed** in 5.62s.

Real loopback HTTP connector service:

```text
python -m pytest -q tests/integration/test_http_json_connector_real.py
```

Result: **8 passed, 0 failed** in 5.02s.

The coverage includes registry/capability validation, S3/Azure connector
contract behavior, ingestion synchronization/checkpoint semantics and bounded
HTTP discovery/fetch/error behavior against a real local service.

## Boundary

This receipt does not claim authenticated S3/Azure/PostgreSQL provider
certification, incremental-source breadth, transactional write conformance or
the complete installed P2 Studio journey. Those provider and family gates
remain open; Public v1 remains **0/13 (0%)**.

