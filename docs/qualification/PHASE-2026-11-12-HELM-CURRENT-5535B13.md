# P14 — Helm/kind exact current-candidate qualification

**Date:** 2026-11-12  
**Candidate SHA:** `5535b13b3fd3e20d7171aafd800c1b2cd9b4618b`  
**Evidence:** `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-helm-qualification-5535b13`  
**Docker evidence:** `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-docker-qualification-5535b13`

The Helm runner passed on Helm `v4.3.1` and kind node `v1.37.0` with Ronin
image digest `sha256:7c57679e60acf821e7697124cf41605d9f1fef4a2e5fa1fbe32855bab3c6a6d7`.

Passed phases: chart lint, rendered-secret boundary, isolated kind cluster,
install/readiness, revision-2 upgrade, rollback to revision 1, health/API,
queued-job persistence, pod restart and queued-job persistence after restart.
Cleanup removed the isolated cluster successfully.

This qualifies the local single-operator Helm operational lane only; it does
not claim multi-user HA, external secret providers or complete P14 release
closure. Public v1 remains **0/13 (0%)**.

