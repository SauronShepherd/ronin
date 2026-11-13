# Qualification receipt — connectors and HTTP ingestion current

- Date: 2026-11-13
- Source checkout: `cd743a41af3ac1b4468045d87dcf3922c3d13ed0`
- Contract command: `python -m pytest -q tests/test_connector_registry.py tests/test_s3_json_connector.py tests/test_azure_blob_json_connector.py tests/test_ingestion_sync.py`.
- Contract result: **84 passed, 0 failed** in 6.12 seconds.
- Real loopback command: `python -m pytest -q tests/integration/test_http_json_connector_real.py`.
- Real loopback result: **8 passed, 0 failed** in 4.66 seconds.
- Combined result: **92 passed, 0 failed**.
- Boundary: registry/capability validation, S3/Azure contracts, ingestion synchronization/checkpoints and bounded HTTP discovery/fetch/error behavior only; no authenticated cloud/PostgreSQL certification, broad incremental-source coverage, transactional writes or complete installed P2 Studio closure.
