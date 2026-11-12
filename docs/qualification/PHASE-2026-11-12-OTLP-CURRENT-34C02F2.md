# P12 — OpenTelemetry Collector real-service qualification

**Date:** 2026-11-12  
**Candidate SHA:** `34c02f2b27198bcc6c2e9e673652baf92ff27a4f`  
**Runner:** `tools/run_otlp_qualification.ps1` in a clean detached worktree  
**Evidence:** `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-otlp-qualification-34c02f2`

## Environment

- Collector image: `otel/opentelemetry-collector-contrib@sha256:45392d534c1edcc809c2d112394029246bc679d2ae5ea7081414a1fc74f2c621`
- Protocol: OTLP/HTTP on loopback
- Qualification mode: clean-candidate
- Cleanup: passed; collector container and temporary worktree removed

## Result

The real collector lane passed **1/1 test, 0 skipped, 0 failed** in 5.13s.
The test exercised traces, metrics and logs ingestion through the pinned
collector and produced JUnit, timing, container-log and JSON qualification
evidence in the external evidence directory.

## Boundary

This receipt qualifies the OTLP transport/collector lane only. It does not
close P12 or Public v1: broad service adoption, alert delivery, cost/budget
behavior, complete product journeys and the remaining family/release gates
remain open.

