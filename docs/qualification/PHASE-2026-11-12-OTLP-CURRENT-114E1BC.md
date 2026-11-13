# OTLP collector real-service qualification — current candidate

**Date:** 2026-11-12  
**Candidate SHA:** `114e1bc35fe9d3f71459bbdf87c9748489587094`  
**Runner:** `tools/run_otlp_qualification.ps1`  
**Collector:** `otel/opentelemetry-collector-contrib@sha256:45392d534c1edcc809c2d112394029246bc679d2ae5ea7081414a1fc74f2c621`

## Result

Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-otlp-qualification-114e1bc-20261112223939`

The real OTLP/HTTP loopback lane passed **1/1 test**, 0 skipped and 0 failed.
The test exercised traces, metrics and logs ingestion through the pinned
collector. The collector was cleaned up after the run.

## Boundary

This closes the current OTLP transport lane only. Broader P12 service
adoption, alert delivery, cost/budget behavior, complete product journeys and
the remaining release gates stay open. Public v1 remains **0/13 (0%) — NO-GO**.
