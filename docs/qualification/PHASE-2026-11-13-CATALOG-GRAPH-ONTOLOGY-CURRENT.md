# Catalog, graph, ontology and bundle contracts — current candidate

**Date:** 2026-11-13  
**Candidate SHA:** `0274e9a926161f28e31fecdb442a44a9f1dd5d94`

## Gate

The selected local P6 surface included all `test_bundle_*.py`,
`test_catalog_*.py` and `test_ontology_*.py` modules plus
`test_quality_bundle_validator_boundaries.py` and
`test_runtime_bundle_portability_survivors.py`.

Result: **314 passed, 0 failed** in 35.99 seconds.

The suite covers bundle IO/import/export/atomicity, catalog ownership/search,
ontology graph/runtime/HTTP/type boundaries, quality validation and runtime
bundle portability survivors.

## Boundary

This is local contract and bundle evidence. PostgreSQL-backed catalog,
authenticated OpenLineage delivery, provider certification and the complete
installed P6 Studio journey remain separate gates. Public v1 remains **0/13
(0%) — NO-GO**.
