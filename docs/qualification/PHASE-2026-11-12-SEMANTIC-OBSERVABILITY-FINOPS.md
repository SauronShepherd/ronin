# Phase receipt — semantic, observability, and FinOps contracts — 2026-11-12

## Candidate

- Source candidate before this receipt: `aea285750edd402015180353cf4dda0f0039852e`.

## Evidence

Executed the focused local surface:

```text
python -m pytest -q tests/test_semantic_joins.py tests/test_semantic_runtime.py tests/test_semantic_store.py tests/test_data_engineering_lineage.py tests/test_ir_rql_openlineage_boundaries.py tests/test_openlineage_export.py tests/test_openlineage_survivor_boundaries.py tests/test_openlineage_transport.py tests/test_alert_state_contract.py tests/test_finops_allocation.py tests/test_finops_forecast.py tests/test_observability_anomaly.py tests/test_observability_finops.py tests/test_observability_instrumentation.py tests/test_quality_alert_signals.py tests/test_quality_observability.py
```

Result: **200 passed in 15.66s**, 0 failures.

The selection covers typed semantic joins/runtime/store behavior, lineage and OpenLineage boundaries/export/transport, alert state contracts, anomaly and quality signals, instrumentation, usage allocation, forecasting, cost/FinOps behavior, and observability integrations at the local contract level.

## Scope boundary

This is local contract evidence. It does not claim complete production service adoption, external notification-provider certification, or a full candidate-bound P10/P12 end-to-end journey. Existing real OTLP evidence remains separately recorded.

## Result

PASS for the selected semantic/observability/FinOps contract surface: **200/200**. P10/P12 and Public V1 remain incomplete; release-qualified progress remains `0/13 (0%)`.
